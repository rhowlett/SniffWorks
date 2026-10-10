/* ==========================================================================
 * [v0.1]
 * i2c_master.c
 * Active I2C master for SNIFF_MODE_MASTER. See i2c_master.h.
 *
 * Polled LL I2C1 on PA9 (SCL) / PA10 (SDA), AF6 open-drain — the same
 * physical pins the sniffer variants observe, so the board wiring table in
 * the user guide is identical for all modes. External pull-ups are assumed
 * (the target bus provides them, as with any master).
 *
 * Every executed command emits one TXN frame per bus phase (a WRITE_READ
 * emits two: the write phase, then the read phase with restart=1), built
 * from the same i2c_txn_t / frame_encode_txn path as the sniffer, so the
 * host log/decode stack does not distinguish master from sniffed traffic.
 * ========================================================================== */
#include "sniffer_config.h"

#if (SNIFF_MODE == SNIFF_MODE_MASTER)

#include "i2c_master.h"
#include "frame_protocol.h"
#include "uart_stream.h"

#include "stm32c0xx_ll_bus.h"
#include "stm32c0xx_ll_gpio.h"
#include "stm32c0xx_ll_i2c.h"

/* ------------------------------------------------------------------------ */
static uint32_t (*s_now_us)(void);
static uint32_t s_txn_count;
static uint32_t s_err_count;
static uint8_t  s_frame_buf[FRAME_MAX_ENCODED];

static void send_frame(uint32_t len)
{
    if (uart_stream_write(s_frame_buf, len) == 0U)
    {
        /* Host link saturated — count it; STATUS.dropped is sniffer-side
         * only, so surface as an error frame if even that fits.            */
        s_err_count++;
    }
}

/* ------------------------------------------------------------------------ */
void i2c_master_init(uint32_t (*now_us)(void))
{
    s_now_us    = now_us;
    s_txn_count = 0U;
    s_err_count = 0U;

    LL_IOP_GRP1_EnableClock(LL_IOP_GRP1_PERIPH_GPIOA);
    LL_APB1_GRP1_EnableClock(LL_APB1_GRP1_PERIPH_I2C1);

    /* PA9 = I2C1_SCL, PA10 = I2C1_SDA, AF6, open-drain, no internal pulls
     * (the bus under test provides pull-ups).                              */
    LL_GPIO_InitTypeDef g = {0};
    g.Pin        = LL_GPIO_PIN_9 | LL_GPIO_PIN_10;
    g.Mode       = LL_GPIO_MODE_ALTERNATE;
    g.Speed      = LL_GPIO_SPEED_FREQ_HIGH;
    g.OutputType = LL_GPIO_OUTPUT_OPENDRAIN;
    g.Pull       = LL_GPIO_PULL_NO;
    g.Alternate  = LL_GPIO_AF_6;
    LL_GPIO_Init(GPIOA, &g);

    LL_I2C_Disable(I2C1);
    LL_I2C_SetTiming(I2C1, MASTER_TIMING_DEFAULT);
    LL_I2C_Enable(I2C1);
}

void i2c_master_set_timing(uint32_t timingr)
{
    LL_I2C_Disable(I2C1);
    LL_I2C_SetTiming(I2C1, timingr);
    LL_I2C_Enable(I2C1);
}

uint32_t i2c_master_txn_count(void)   { return s_txn_count; }
uint32_t i2c_master_error_count(void) { return s_err_count; }

/* ------------------------------------------------------------------------ */
/* Low-level polled transfer helpers                                         */
/* ------------------------------------------------------------------------ */
static uint8_t wait_flag(uint32_t (*is_set)(const I2C_TypeDef *),
                         uint32_t deadline_us, uint8_t *timed_out)
{
    while (is_set(I2C1) == 0U)
    {
        if (LL_I2C_IsActiveFlag_NACK(I2C1) != 0U)
        {
            return 0U;                          /* NACK detected            */
        }
        if ((int32_t)(s_now_us() - deadline_us) >= 0)
        {
            *timed_out = 1U;
            return 0U;
        }
    }
    return 1U;
}

static void bus_recover(void)
{
    /* Clear error/stop state and re-arm the peripheral after a fault.      */
    LL_I2C_ClearFlag_NACK(I2C1);
    LL_I2C_ClearFlag_STOP(I2C1);
    if (LL_I2C_IsActiveFlag_BERR(I2C1) || LL_I2C_IsActiveFlag_ARLO(I2C1))
    {
        LL_I2C_ClearFlag_BERR(I2C1);
        LL_I2C_ClearFlag_ARLO(I2C1);
        s_err_count++;
        send_frame(frame_encode_error(s_frame_buf, ERR_CODE_BUS_ERROR, 0U));
    }
    LL_I2C_Disable(I2C1);
    LL_I2C_Enable(I2C1);
}

/* One write phase. stop=1 -> AUTOEND (STOP after last byte);
 * stop=0 -> SOFTEND (leave bus armed for a repeated-start read).
 * Fills txn; returns 1 on full ACKed transfer.                             */
static uint8_t phase_write(uint8_t addr7, const uint8_t *data, uint8_t len,
                           uint8_t stop, i2c_txn_t *txn)
{
    uint8_t  timed_out = 0U;
    uint32_t deadline  = s_now_us() + MASTER_TIMEOUT_US;

    txn->t_us     = s_now_us();
    txn->addr7    = addr7;
    txn->dir_read = 0U;
    txn->restart  = 0U;
    txn->stop     = stop;
    txn->overflow = 0U;
    txn->timeout  = 0U;
    txn->framing  = 0U;
    txn->scl_sum_us = 0U;                   /* master: not measured */
    txn->scl_cnt    = 0U;
    txn->nak      = 0U;
    txn->len      = len;
    for (uint8_t i = 0U; i < len; i++) { txn->data[i] = data[i]; }

    LL_I2C_HandleTransfer(I2C1, (uint32_t)addr7 << 1, LL_I2C_ADDRSLAVE_7BIT,
                          len,
                          stop ? LL_I2C_MODE_AUTOEND : LL_I2C_MODE_SOFTEND,
                          LL_I2C_GENERATE_START_WRITE);

    for (uint8_t i = 0U; i < len; i++)
    {
        if (wait_flag(LL_I2C_IsActiveFlag_TXIS, deadline, &timed_out) == 0U)
        {
            goto fail;
        }
        LL_I2C_TransmitData8(I2C1, data[i]);
    }
    if (stop)
    {
        if (wait_flag(LL_I2C_IsActiveFlag_STOP, deadline, &timed_out) == 0U)
        {
            goto fail;
        }
        LL_I2C_ClearFlag_STOP(I2C1);
    }
    else
    {
        if (wait_flag(LL_I2C_IsActiveFlag_TC, deadline, &timed_out) == 0U)
        {
            goto fail;
        }
    }
    return 1U;

fail:
    txn->nak     = (uint8_t)(LL_I2C_IsActiveFlag_NACK(I2C1) != 0U);
    txn->timeout = timed_out;
    txn->stop    = 1U;                          /* bus is released below    */
    bus_recover();
    return 0U;
}

/* One read phase (always ends in STOP). restart=1 when it follows a
 * SOFTEND write.                                                            */
static uint8_t phase_read(uint8_t addr7, uint8_t rlen, uint8_t restart,
                          i2c_txn_t *txn)
{
    uint8_t  timed_out = 0U;
    uint32_t deadline  = s_now_us() + MASTER_TIMEOUT_US;

    if (rlen > TXN_MAX_DATA) { rlen = TXN_MAX_DATA; }

    txn->t_us     = s_now_us();
    txn->addr7    = addr7;
    txn->dir_read = 1U;
    txn->restart  = restart;
    txn->stop     = 1U;
    txn->overflow = 0U;
    txn->timeout  = 0U;
    txn->framing  = 0U;
    txn->scl_sum_us = 0U;                   /* master: not measured */
    txn->scl_cnt    = 0U;
    txn->nak      = 0U;
    txn->len      = 0U;

    LL_I2C_HandleTransfer(I2C1, (uint32_t)addr7 << 1, LL_I2C_ADDRSLAVE_7BIT,
                          rlen, LL_I2C_MODE_AUTOEND,
                          LL_I2C_GENERATE_START_READ);

    for (uint8_t i = 0U; i < rlen; i++)
    {
        if (wait_flag(LL_I2C_IsActiveFlag_RXNE, deadline, &timed_out) == 0U)
        {
            goto fail;
        }
        txn->data[txn->len++] = LL_I2C_ReceiveData8(I2C1);
    }
    if (wait_flag(LL_I2C_IsActiveFlag_STOP, deadline, &timed_out) == 0U)
    {
        goto fail;
    }
    LL_I2C_ClearFlag_STOP(I2C1);
    return 1U;

fail:
    txn->nak     = (uint8_t)(LL_I2C_IsActiveFlag_NACK(I2C1) != 0U);
    txn->timeout = timed_out;
    bus_recover();
    return 0U;
}

/* ------------------------------------------------------------------------ */
/* Command execution                                                         */
/* ------------------------------------------------------------------------ */
void i2c_master_exec(uint8_t cmd, const uint8_t *payload, uint8_t len)
{
    i2c_txn_t txn;

    switch (cmd)
    {
        case CMD_I2C_WRITE:                     /* addr7, data[]            */
        {
            if (len < 1U)                       { goto bad; }
            uint8_t dlen = (uint8_t)(len - 1U);
            if (dlen > TXN_MAX_DATA)            { goto bad; }
            phase_write(payload[0] & 0x7FU, &payload[1], dlen, 1U, &txn);
            s_txn_count++;
            send_frame(frame_encode_txn(s_frame_buf, &txn));
            break;
        }

        case CMD_I2C_WRITE_READ:                /* addr7, wlen, wdata, rlen */
        {
            if (len < 3U)                       { goto bad; }
            uint8_t addr = payload[0] & 0x7FU;
            uint8_t wlen = payload[1];
            if ((uint32_t)wlen + 3U != len || wlen > TXN_MAX_DATA)
            {
                goto bad;
            }
            uint8_t rlen = payload[2U + wlen];

            uint8_t ok = phase_write(addr, &payload[2], wlen, 0U, &txn);
            s_txn_count++;
            send_frame(frame_encode_txn(s_frame_buf, &txn));
            if (ok)
            {
                phase_read(addr, rlen, 1U, &txn);
                s_txn_count++;
                send_frame(frame_encode_txn(s_frame_buf, &txn));
            }
            break;
        }

        case CMD_I2C_READ:                      /* addr7, rlen              */
        {
            if (len != 2U)                      { goto bad; }
            phase_read(payload[0] & 0x7FU, payload[1], 0U, &txn);
            s_txn_count++;
            send_frame(frame_encode_txn(s_frame_buf, &txn));
            break;
        }

        case CMD_SET_BUS_SPEED:                 /* 0=100 kHz, 1=400 kHz     */
        {
            if (len != 1U || payload[0] > 1U)   { goto bad; }
            i2c_master_set_timing(payload[0] ? MASTER_TIMING_400K
                                             : MASTER_TIMING_100K);
            /* Ack with a STATUS frame (host expects one per the spec).     */
            /* main.c sends STATUS on our behalf via its shared path.       */
            break;
        }

        default:
            goto bad;
    }
    return;

bad:
    s_err_count++;
    send_frame(frame_encode_error(s_frame_buf, ERR_CODE_BAD_COMMAND, cmd));
}

#endif /* SNIFF_MODE_MASTER */
