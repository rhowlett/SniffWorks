/**
 * [v0.2]
 * @file    dut_app.c
 * @brief   NUCLEO-H533RE loopback DUT: I2C1 master drives test patterns that
 *          the PC sends; I2C2 (R1) and I2C3 (R2) answer as responders with the
 *          synthetic register map. All three sit on ONE external bus, which
 *          the sniffers under test also watch.
 *
 *          Isolated instrument: shares no code with the sniffer tools.
 *          Protocol: loopback_dut/docs/PROTOCOL.md. Register map: dut_regmap.h.
 *
 * Concurrency model
 *   - Main loop: UART line assembly, command execution, master transfers
 *     (interrupt-driven HAL Seq API, waited on with a TIM2 timeout).
 *   - I2C2/I2C3 ISRs: responder byte streams (HAL listen + Seq, one byte at a
 *     time so the stream can be computed on the fly and clock stretching can
 *     be injected before any byte).
 *   - Clock-stretch injection busy-waits inside the responder ISR: the HAL
 *     clears ADDR / loads TXDR only after the callback returns, so SCL is held
 *     low for the wait. Stretch therefore happens at byte boundaries only; a
 *     hardware I2C slave cannot stretch mid-byte.
 */
#include <stdio.h>
#include <string.h>

#include "main.h"
#include "i2c.h"
#include "usart.h"
#include "tim.h"

#include "loopback_config.h"
#include "dut_app.h"
#include "dut_proto.h"
#include "dut_regmap.h"
#include "dut_timing.h"

/* =========================================================== time base */
static inline uint32_t now_us(void) { return __HAL_TIM_GET_COUNTER(&htim2); }

static void delay_us(uint32_t us)
{
    const uint32_t t0 = now_us();
    while ((now_us() - t0) < us) { }
}

/* ========================================================== UART output */
static char s_out[LB_LINE_MAX + 16U];

static void out_send(size_t len)
{
    const size_t n = dut_line_seal(s_out, len, sizeof s_out);
    if (n != 0U)
    {
        (void)HAL_UART_Transmit(&huart2, (uint8_t *)s_out, (uint16_t)n, 200U);
    }
}

#define OUTF(...) do { int _n = snprintf(s_out, sizeof s_out - 6U, __VA_ARGS__); \
                       if (_n > 0) { out_send((size_t)_n); } } while (0)

/* =========================================================== UART input */
static uint8_t           s_rx_byte;
static volatile uint8_t  s_rx_ring[1024];
static volatile uint16_t s_rx_head, s_rx_tail;
static volatile uint32_t s_rx_overrun;
static char              s_line[LB_LINE_MAX + 8U];
static uint16_t          s_line_len;
static uint8_t           s_line_drop;       /* discarding an over-long line */

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)
{
    if (huart->Instance == USART2)
    {
        const uint16_t next = (uint16_t)((s_rx_head + 1U) % sizeof s_rx_ring);
        if (next != s_rx_tail) { s_rx_ring[s_rx_head] = s_rx_byte; s_rx_head = next; }
        else                   { s_rx_overrun++; }
        (void)HAL_UART_Receive_IT(&huart2, &s_rx_byte, 1U);
    }
}

void HAL_UART_ErrorCallback(UART_HandleTypeDef *huart)
{
    if (huart->Instance == USART2)
    {
        s_rx_overrun++;
        (void)HAL_UART_Receive_IT(&huart2, &s_rx_byte, 1U);
    }
}

/* ============================================================ responders */
typedef struct
{
    I2C_HandleTypeDef *h;
    uint8_t      id;            /* 1 = I2C2, 2 = I2C3                        */
    uint8_t      addr7;
    uint8_t      enabled;
    dut_regmap_t map;
    uint8_t      pec_after;     /* append PEC after n read bytes (0 = off)   */
    uint8_t      stretch_at;    /* byte index for stretch                    */
    uint16_t     stretch_us;    /* 0 = off                                   */
    /* per-phase ISR state                                                   */
    uint32_t     k;             /* bytes moved in this phase                 */
    uint8_t      rx, tx;
    uint8_t      crc;           /* running SMBus PEC of the transaction      */
    uint8_t      in_write;      /* last phase was a write not yet STOPped    */
    /* counters                                                              */
    volatile uint32_t n_writes, n_reads, n_bytes_rx, n_bytes_tx, n_err;
} resp_t;

static resp_t s_resp[2];

static resp_t *resp_of(const I2C_HandleTypeDef *h)
{
    if (h == &hi2c2) { return &s_resp[0]; }
    if (h == &hi2c3) { return &s_resp[1]; }
    return 0;
}

static void maybe_stretch(const resp_t *r)
{
    if ((r->stretch_us != 0U) && (r->k == r->stretch_at))
    {
        delay_us(r->stretch_us);            /* SCL held low meanwhile       */
    }
}

/* next byte the responder puts on the bus during a read phase             */
static uint8_t next_tx(resp_t *r)
{
    uint8_t b;
    if ((r->pec_after != 0U) && (r->k == r->pec_after))
    {
        b = r->crc;                          /* PEC over the whole txn       */
    }
    else
    {
        const uint32_t idx = ((r->pec_after != 0U) && (r->k > r->pec_after))
                             ? (r->k - 1U) : r->k;
        b = dut_regmap_read(&r->map, idx);
    }
    r->crc = dut_crc8_update(r->crc, b);
    return b;
}

void HAL_I2C_AddrCallback(I2C_HandleTypeDef *hi2c, uint8_t TransferDirection,
                          uint16_t AddrMatchCode)
{
    (void)AddrMatchCode;
    resp_t *r = resp_of(hi2c);
    if (r == 0) { return; }
    r->k = 0U;
    if (TransferDirection == I2C_DIRECTION_TRANSMIT)        /* master writes */
    {
        r->crc = dut_crc8_update(0U, (uint8_t)(r->addr7 << 1));
        r->in_write = 1U;
        r->n_writes++;
        maybe_stretch(r);
        (void)HAL_I2C_Slave_Seq_Receive_IT(hi2c, &r->rx, 1U, I2C_FIRST_FRAME);
    }
    else                                                     /* master reads  */
    {
        const uint8_t a = (uint8_t)((r->addr7 << 1) | 1U);
        /* PEC spans Addr+W, command, Sr Addr+R, data (SMBus 3.x 6.4) when   */
        /* this read follows a write with no STOP in between                  */
        r->crc = r->in_write ? dut_crc8_update(r->crc, a) : dut_crc8_update(0U, a);
        r->in_write = 0U;
        r->n_reads++;
        r->tx = next_tx(r);
        maybe_stretch(r);
        (void)HAL_I2C_Slave_Seq_Transmit_IT(hi2c, &r->tx, 1U, I2C_FIRST_FRAME);
    }
}

void HAL_I2C_SlaveRxCpltCallback(I2C_HandleTypeDef *hi2c)
{
    resp_t *r = resp_of(hi2c);
    if (r == 0) { return; }
    dut_regmap_write(&r->map, r->k, r->rx);
    r->crc = dut_crc8_update(r->crc, r->rx);
    r->n_bytes_rx++;
    r->k++;
    maybe_stretch(r);
    (void)HAL_I2C_Slave_Seq_Receive_IT(hi2c, &r->rx, 1U, I2C_NEXT_FRAME);
}

void HAL_I2C_SlaveTxCpltCallback(I2C_HandleTypeDef *hi2c)
{
    resp_t *r = resp_of(hi2c);
    if (r == 0) { return; }
    r->n_bytes_tx++;
    r->k++;
    r->tx = next_tx(r);
    maybe_stretch(r);
    (void)HAL_I2C_Slave_Seq_Transmit_IT(hi2c, &r->tx, 1U, I2C_NEXT_FRAME);
}

void HAL_I2C_ListenCpltCallback(I2C_HandleTypeDef *hi2c)
{
    resp_t *r = resp_of(hi2c);
    if (r == 0) { return; }
    r->in_write = 0U;                        /* STOP ends the transaction    */
    if (r->enabled) { (void)HAL_I2C_EnableListen_IT(hi2c); }
}

/* ================================================================ master */
static volatile uint8_t  s_m_done, s_m_err;
static volatile uint32_t s_m_errcode;
static uint32_t          s_scl_hz = LB_DEFAULT_SCL_HZ;
static dut_timing_env_t  s_env = { LB_I2C_KERNEL_HZ, LB_RISE_NS, LB_FALL_NS, LB_TAF_NS };
static dut_timing_t      s_tim;
static uint8_t           s_mbuf[LB_MAX_XFER];
static volatile uint32_t s_n_err;

void HAL_I2C_MasterTxCpltCallback(I2C_HandleTypeDef *hi2c) { if (hi2c == &hi2c1) { s_m_done = 1U; } }
void HAL_I2C_MasterRxCpltCallback(I2C_HandleTypeDef *hi2c) { if (hi2c == &hi2c1) { s_m_done = 1U; } }

void HAL_I2C_ErrorCallback(I2C_HandleTypeDef *hi2c)
{
    if (hi2c == &hi2c1)
    {
        s_m_errcode = HAL_I2C_GetError(hi2c);
        s_m_err = 1U;
        return;
    }
    resp_t *r = resp_of(hi2c);
    if (r == 0) { return; }
    /* AF = the master NAKed our byte: the normal end of a read phase       */
    if ((HAL_I2C_GetError(hi2c) & ~HAL_I2C_ERROR_AF) != 0U) { r->n_err++; }
}

static void apply_timing_to(I2C_HandleTypeDef *h, uint32_t timingr)
{
    __HAL_I2C_DISABLE(h);
    h->Init.Timing = timingr;
    h->Instance->TIMINGR = timingr;
    __HAL_I2C_ENABLE(h);
}

/* I2C1 is master only: its own address 0x08 is configured (CubeMX) but NOT
 * enabled for matching, so it can never ACK/stretch; 0x08 is the rig's
 * deterministic address-NAK target.                                        */
static void master_disable_own_address(void)
{
    CLEAR_BIT(hi2c1.Instance->OAR1, I2C_OAR1_OA1EN);
}

static void master_recover(void)
{
    (void)HAL_I2C_DeInit(&hi2c1);
    (void)HAL_I2C_Init(&hi2c1);
    (void)HAL_I2CEx_ConfigAnalogFilter(&hi2c1, I2C_ANALOGFILTER_ENABLE);
    apply_timing_to(&hi2c1, s_tim.timingr);
    master_disable_own_address();
}

typedef enum { PH_OK = 0, PH_NAK_ADDR, PH_NAK_DATA, PH_ERR } ph_result_t;

static uint32_t phase_timeout_us(uint32_t nbytes)
{
    const uint64_t bits = (uint64_t)(nbytes + 1U) * 9U;
    return (uint32_t)(LB_XFER_TIMEOUT_MS * 1000U + (bits * 1000000U) / s_scl_hz)
           + 2U * LB_MAX_STRETCH_US;
}

static ph_result_t master_wait(uint32_t nbytes)
{
    const uint32_t t0 = now_us(), tmo = phase_timeout_us(nbytes);
    while ((s_m_done == 0U) && (s_m_err == 0U))
    {
        if ((now_us() - t0) > tmo)
        {
            (void)HAL_I2C_Master_Abort_IT(&hi2c1, 0U);
            master_recover();
            s_n_err++;
            return PH_ERR;
        }
    }
    if (s_m_err != 0U)
    {
        if ((s_m_errcode & HAL_I2C_ERROR_AF) != 0U)
        {
            /* Address NAK vs data NAK. The H5 HAL Seq transmit PRELOADS the
             * first byte into TXDR before START (XferCount already -1), so
             * "nothing sent" means at most one byte consumed. A NAK on data
             * byte 0 of a 1-byte write is indistinguishable from an address
             * NAK here; the rig's responders always ACK data, so it is
             * reported as NA. (Fixed 2026-10-02: every address NAK was
             * reported as ND.)                                              */
            return ((uint32_t)(hi2c1.XferSize - hi2c1.XferCount) <= 1U)
                   ? PH_NAK_ADDR : PH_NAK_DATA;
        }
        master_recover();
        s_n_err++;
        return PH_ERR;
    }
    return PH_OK;
}

static ph_result_t master_write(uint8_t addr7, const uint8_t *d, uint16_t n, uint32_t opt)
{
    s_m_done = 0U; s_m_err = 0U; s_m_errcode = 0U;
    memcpy(s_mbuf, d, n);
    if (HAL_I2C_Master_Seq_Transmit_IT(&hi2c1, (uint16_t)(addr7 << 1), s_mbuf, n, opt) != HAL_OK)
    {
        master_recover();
        return PH_ERR;
    }
    return master_wait(n);
}

static ph_result_t master_read(uint8_t addr7, uint16_t n, uint32_t opt)
{
    s_m_done = 0U; s_m_err = 0U; s_m_errcode = 0U;
    memset(s_mbuf, 0, n);
    if (HAL_I2C_Master_Seq_Receive_IT(&hi2c1, (uint16_t)(addr7 << 1), s_mbuf, n, opt) != HAL_OK)
    {
        master_recover();
        return PH_ERR;
    }
    return master_wait(n);
}

static void wait_bus_idle(void)
{
    const uint32_t t0 = now_us();
    while (__HAL_I2C_GET_FLAG(&hi2c1, I2C_FLAG_BUSY) && ((now_us() - t0) < 5000U)) { }
}

/* ============================================================ reporting */
static const char *ack_str(ph_result_t r)
{
    switch (r)
    {
        case PH_OK:       return "A";
        case PH_NAK_ADDR: return "NA";
        case PH_NAK_DATA: return "ND";
        default:          return "ER";
    }
}

/* PH <seq> <iter> <idx> <S|SR> <aa> <W|R> <A|NA|ND|ER> <P|-> <n> <hex..>   */
static void report_phase(uint32_t seq, uint32_t iter, uint32_t idx, int restart,
                         uint8_t addr7, int rd, ph_result_t res, int stop,
                         const uint8_t *d, uint16_t n)
{
    int len = snprintf(s_out, sizeof s_out - 6U, "PH %lu %lu %lu %s %02X %c %s %c %u",
                       (unsigned long)seq, (unsigned long)iter, (unsigned long)idx,
                       restart ? "SR" : "S", addr7, rd ? 'R' : 'W', ack_str(res),
                       stop ? 'P' : '-', (unsigned)((res == PH_NAK_ADDR) ? 0U : n));
    if (res != PH_NAK_ADDR)
    {
        for (uint16_t i = 0U; (i < n) && (len + 3 < (int)sizeof s_out - 6); i++)
        {
            len += snprintf(&s_out[len], sizeof s_out - 6U - (size_t)len, " %02X", d[i]);
        }
    }
    out_send((size_t)len);
}

/* ================================================================== RUN */
static void do_run(const dut_cmd_t *c)
{
    for (uint32_t it = 0U; it < c->rep; it++)
    {
        const uint32_t t0 = now_us();
        ph_result_t r1 = PH_OK, r2 = PH_OK;
        wait_bus_idle();
        HAL_GPIO_WritePin(DUT_SYNC_GPIO_Port, DUT_SYNC_Pin, GPIO_PIN_SET);

        switch (c->op)
        {
            case DUT_OP_W:
                r1 = master_write(c->addr, c->wdata, c->wlen, I2C_FIRST_AND_LAST_FRAME);
                report_phase(c->seq, it, 0U, 0, c->addr, 0, r1, 1, c->wdata, c->wlen);
                break;
            case DUT_OP_R:
                r1 = master_read(c->addr, c->rlen, I2C_FIRST_AND_LAST_FRAME);
                report_phase(c->seq, it, 0U, 0, c->addr, 1, r1, 1, s_mbuf, c->rlen);
                break;
            case DUT_OP_WR:
                r1 = master_write(c->addr, c->wdata, c->wlen, I2C_FIRST_FRAME);
                if (r1 == PH_OK)
                {
                    report_phase(c->seq, it, 0U, 0, c->addr, 0, r1, 0, c->wdata, c->wlen);
                    r2 = master_read(c->addr, c->rlen, I2C_LAST_FRAME);
                    report_phase(c->seq, it, 1U, 1, c->addr, 1, r2, 1, s_mbuf, c->rlen);
                }
                else
                {   /* NAK on the write phase: HAL ends the transfer with STOP */
                    report_phase(c->seq, it, 0U, 0, c->addr, 0, r1, 1, c->wdata, c->wlen);
                }
                break;
            case DUT_OP_WPR:
                r1 = master_write(c->addr, c->wdata, c->wlen, I2C_FIRST_AND_LAST_FRAME);
                report_phase(c->seq, it, 0U, 0, c->addr, 0, r1, 1, c->wdata, c->wlen);
                if (r1 == PH_OK)
                {
                    wait_bus_idle();
                    r2 = master_read(c->addr, c->rlen, I2C_FIRST_AND_LAST_FRAME);
                    report_phase(c->seq, it, 1U, 0, c->addr, 1, r2, 1, s_mbuf, c->rlen);
                }
                break;
            default:
                break;
        }

        HAL_GPIO_WritePin(DUT_SYNC_GPIO_Port, DUT_SYNC_Pin, GPIO_PIN_RESET);
        const ph_result_t worst = (r1 != PH_OK) ? r1 : r2;
        if (worst != PH_OK)
        {   /* a NAKed/failed phase must not leave the bus claimed          */
            wait_bus_idle();
            if (__HAL_I2C_GET_FLAG(&hi2c1, I2C_FLAG_BUSY)) { master_recover(); s_n_err++; }
        }
        OUTF("END %lu %lu %s t=%lu dur=%lu", (unsigned long)c->seq, (unsigned long)it,
             (worst == PH_OK) ? "OK" : (worst == PH_ERR) ? "ERR" : "NAK",
             (unsigned long)t0, (unsigned long)(now_us() - t0));
        if (c->gap_us != 0U) { delay_us(c->gap_us); }
    }
}

/* ============================================================== SET/etc */
static void resp_apply(resp_t *r)
{
    (void)HAL_I2C_DisableListen_IT(r->h);
    __HAL_I2C_DISABLE(r->h);
    r->h->Init.OwnAddress1 = (uint32_t)r->addr7 << 1;
    CLEAR_BIT(r->h->Instance->OAR1, I2C_OAR1_OA1EN);
    MODIFY_REG(r->h->Instance->OAR1, I2C_OAR1_OA1, r->h->Init.OwnAddress1);
    if (r->enabled) { SET_BIT(r->h->Instance->OAR1, I2C_OAR1_OA1EN); }
    __HAL_I2C_ENABLE(r->h);
    r->h->State = HAL_I2C_STATE_READY;
    if (r->enabled) { (void)HAL_I2C_EnableListen_IT(r->h); }
}

static void report_speed(void)
{
    OUTF("OK SPEED hz=%lu pred=%lu timingr=%08lX presc=%u scll=%u sclh=%u sdadel=%u scldel=%u rise=%lu fall=%lu",
         (unsigned long)s_scl_hz, (unsigned long)s_tim.predicted_hz,
         (unsigned long)s_tim.timingr, s_tim.presc, s_tim.scll, s_tim.sclh,
         s_tim.sdadel, s_tim.scldel, (unsigned long)s_env.rise_ns,
         (unsigned long)s_env.fall_ns);
}

static int set_speed(uint32_t hz, uint32_t rise, uint32_t fall)
{
    dut_timing_env_t env = s_env;
    dut_timing_t t;
    env.rise_ns = rise;
    env.fall_ns = fall;
    if (dut_timing_compute(&env, hz, &t) != 0) { return -1; }
    s_env = env;
    s_tim = t;
    s_scl_hz = hz;
    wait_bus_idle();
    apply_timing_to(&hi2c1, t.timingr);
    for (int i = 0; i < 2; i++)
    {   /* responders use SDADEL/SCLDEL for their data output timing        */
        (void)HAL_I2C_DisableListen_IT(s_resp[i].h);
        apply_timing_to(s_resp[i].h, t.timingr);
        s_resp[i].h->State = HAL_I2C_STATE_READY;
        if (s_resp[i].enabled) { (void)HAL_I2C_EnableListen_IT(s_resp[i].h); }
    }
    return 0;
}

static void report_status(void)
{
    OUTF("STATUS proto=%u fw=%u.%u hz=%lu pred=%lu r1=%02X:%u r2=%02X:%u "
         "pec=%u,%u stretch=%u@%u,%u@%u r1w=%lu r1r=%lu r2w=%lu r2r=%lu "
         "rerr=%lu,%lu merr=%lu uart_ovr=%lu",
         LB_PROTO_VERSION, LB_FW_MAJOR, LB_FW_MINOR,
         (unsigned long)s_scl_hz, (unsigned long)s_tim.predicted_hz,
         s_resp[0].addr7, s_resp[0].enabled, s_resp[1].addr7, s_resp[1].enabled,
         s_resp[0].pec_after, s_resp[1].pec_after,
         s_resp[0].stretch_us, s_resp[0].stretch_at, s_resp[1].stretch_us, s_resp[1].stretch_at,
         (unsigned long)s_resp[0].n_writes, (unsigned long)s_resp[0].n_reads,
         (unsigned long)s_resp[1].n_writes, (unsigned long)s_resp[1].n_reads,
         (unsigned long)s_resp[0].n_err, (unsigned long)s_resp[1].n_err,
         (unsigned long)s_n_err, (unsigned long)s_rx_overrun);
}

static void resp_reset(resp_t *r, I2C_HandleTypeDef *h, uint8_t id,
                       uint8_t addr7, uint16_t base)
{
    memset(r, 0, sizeof *r);
    r->h = h;
    r->id = id;
    r->addr7 = addr7;
    r->enabled = 1U;
    dut_regmap_init(&r->map, base);
}

static void hello(void)
{
    OUTF("HELLO LBDUT proto=%u fw=%u.%u kernel=%lu", LB_PROTO_VERSION,
         LB_FW_MAJOR, LB_FW_MINOR, (unsigned long)LB_I2C_KERNEL_HZ);
}

static void execute(char *line)
{
    static dut_cmd_t c;
    const dut_err_t e = dut_parse_line(line, &c);
    if (e != DUT_OK)
    {
        static const char *const names[] = { "OK", "SYNTAX", "CRC", "ARG", "LONG" };
        OUTF("ERR - %u %s", (unsigned)e, names[(e <= DUT_E_LONG) ? e : 0]);
        return;
    }
    resp_t *r = (c.resp >= 1U && c.resp <= 2U) ? &s_resp[c.resp - 1U] : 0;
    switch (c.type)
    {
        case DUT_CMD_NONE:   break;
        case DUT_CMD_PING:   hello(); break;
        case DUT_CMD_STATUS: report_status(); break;
        case DUT_CMD_RESET:
            resp_reset(&s_resp[0], &hi2c2, 1U, LB_R1_ADDR, LB_R1_WORD_BASE);
            resp_reset(&s_resp[1], &hi2c3, 2U, LB_R2_ADDR, LB_R2_WORD_BASE);
            resp_apply(&s_resp[0]);
            resp_apply(&s_resp[1]);
            s_n_err = 0U; s_rx_overrun = 0U;
            (void)set_speed(LB_DEFAULT_SCL_HZ, LB_RISE_NS, LB_FALL_NS);
            OUTF("OK RESET");
            break;
        case DUT_CMD_SET_SPEED:
            if (set_speed(c.v1, c.v2, c.v3) != 0) { OUTF("ERR - 3 SPEED infeasible"); }
            else { report_speed(); }
            break;
        case DUT_CMD_SET_ADDR:
            if ((uint8_t)c.v1 == s_resp[(c.resp == 1U) ? 1 : 0].addr7)
            {
                OUTF("ERR - 3 ADDR clashes with other responder");
                break;
            }
            r->addr7 = (uint8_t)c.v1;
            resp_apply(r);
            OUTF("OK ADDR %u %02X", c.resp, r->addr7);
            break;
        case DUT_CMD_SET_EN:
            r->enabled = (uint8_t)c.v1;
            resp_apply(r);
            OUTF("OK EN %u %u", c.resp, r->enabled);
            break;
        case DUT_CMD_SET_PEC:
            r->pec_after = (uint8_t)c.v1;
            OUTF("OK PEC %u %u", c.resp, r->pec_after);
            break;
        case DUT_CMD_SET_STRETCH:
            r->stretch_at = (uint8_t)c.v1;
            r->stretch_us = (uint16_t)c.v2;
            OUTF("OK STRETCH %u %u %u", c.resp, r->stretch_at, r->stretch_us);
            break;
        case DUT_CMD_RUN:
            do_run(&c);
            break;
        default:
            OUTF("ERR - 1 SYNTAX");
            break;
    }
}

/* ============================================================== public */
void dut_app_init(void)
{
    (void)HAL_TIM_Base_Start(&htim2);

    master_disable_own_address();
    resp_reset(&s_resp[0], &hi2c2, 1U, LB_R1_ADDR, LB_R1_WORD_BASE);
    resp_reset(&s_resp[1], &hi2c3, 2U, LB_R2_ADDR, LB_R2_WORD_BASE);
    (void)set_speed(LB_DEFAULT_SCL_HZ, LB_RISE_NS, LB_FALL_NS);
    resp_apply(&s_resp[0]);
    resp_apply(&s_resp[1]);

    (void)HAL_UART_Receive_IT(&huart2, &s_rx_byte, 1U);
    hello();
}

void dut_app_poll(void)
{
    static uint32_t last_blink;

    /* line assembly */
    while (s_rx_tail != s_rx_head)
    {
        const char ch = (char)s_rx_ring[s_rx_tail];
        s_rx_tail = (uint16_t)((s_rx_tail + 1U) % sizeof s_rx_ring);
        if (ch == '\r') { continue; }
        if (ch == '\n')
        {
            if (s_line_drop) { OUTF("ERR - 4 LONG"); }
            else { s_line[s_line_len] = '\0'; execute(s_line); }
            s_line_len = 0U;
            s_line_drop = 0U;
            continue;
        }
        if (s_line_len < LB_LINE_MAX) { s_line[s_line_len++] = ch; }
        else                          { s_line_drop = 1U; }
    }

    /* watchdog: a responder that fell out of LISTEN is re-armed            */
    for (int i = 0; i < 2; i++)
    {
        if (s_resp[i].enabled && (HAL_I2C_GetState(s_resp[i].h) == HAL_I2C_STATE_READY))
        {
            (void)HAL_I2C_EnableListen_IT(s_resp[i].h);
        }
    }

    /* heartbeat */
    if ((now_us() - last_blink) > 500000U)
    {
        last_blink = now_us();
        HAL_GPIO_TogglePin(LD2_GPIO_Port, LD2_Pin);
    }
}
