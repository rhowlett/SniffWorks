/**
 * [v0.3]
 ******************************************************************************
 * @file    main.c
 * @brief   NUCLEO-C031C6 I2C sniffer firmware - entry point and superloop.
 *
 * Architecture
 * ------------
 * ZERO interrupts. Everything runs in one deterministic superloop so the
 * bit-bang sampler never suffers ISR jitter:
 *
 *   1. sample SCL/SDA + decode           (every iteration, hot path)
 *   2. extend the 16-bit us timer        (every iteration, 2 reg reads)
 *   3. pump UART TX DMA                  (every 64 iterations)
 *   4. poll host commands                (every 64 iterations)
 *   5. 1 Hz STATUS frame + LED heartbeat (time-based)
 *   fw 1.4: steps 3-5 are deferred while a bus transaction is open
 *   (SNIFF_DEFER_UPKEEP, review B30) and the hot path is instrumented with
 *   TIM14 (SNIFF_DIAG): see sniffer_config.h.
 *
 * Timestamps: TIM3 free-runs at 1 MHz (16-bit); software extends it to
 * 32 bits by polling the update flag - safe because the loop period is
 * orders of magnitude shorter than the 65.536 ms rollover.
 *
 * Board bring-up: 48 MHz HSI48 (HSIDIV=1), flash latency 1 WS.
 * LED LD4 (PA5) heartbeats while idle, solid during capture.
 ******************************************************************************
 */
#include "stm32c0xx.h"
#include "stm32c0xx_ll_bus.h"
#include "stm32c0xx_ll_rcc.h"
#include "stm32c0xx_ll_system.h"
#include "stm32c0xx_ll_gpio.h"
#include "stm32c0xx_ll_tim.h"
#include "stm32c0xx_ll_utils.h"

#include "sniffer_config.h"
#include "i2c_bitbang_decoder.h"
#include "sniffer_slave_monitor.h"
#include "i2c_master.h"
#include "frame_protocol.h"
#include "uart_stream.h"
#include "edge_ring.h"

/* fw 1.6: bit-bang sampling by EXTI edge interrupt + edge ring (B30/B31)  */
#define SNIFF_EDGE_MODE  ((SNIFF_MODE == SNIFF_MODE_BITBANG) && (SNIFF_EDGE_IRQ != 0))
#if SNIFF_EDGE_MODE && ((SNIFF_DIAG != 0) || (SNIFF_DEFER_UPKEEP != 0))
#error "SNIFF_DIAG / SNIFF_DEFER_UPKEEP instrument the polled loop: build them with SNIFF_EDGE_IRQ=0"
#endif

/* --------------------------------------------------------------------------
 * Timestamping: TIM3 @ 1 MHz, software-extended to 32 bits
 * ------------------------------------------------------------------------ */
static uint32_t s_ts_high;   /* accumulated microseconds from rollovers     */

static void timestamp_init(void)
{
    LL_APB1_GRP1_EnableClock(LL_APB1_GRP1_PERIPH_TIM3);
    LL_TIM_SetPrescaler(TIM3, (SYSCLK_HZ / 1000000U) - 1U);   /* 1 us tick  */
    LL_TIM_SetAutoReload(TIM3, 0xFFFFU);
    LL_TIM_SetCounterMode(TIM3, LL_TIM_COUNTERMODE_UP);
    LL_TIM_GenerateEvent_UPDATE(TIM3);          /* latch prescaler          */
    LL_TIM_ClearFlag_UPDATE(TIM3);
    LL_TIM_EnableCounter(TIM3);
    s_ts_high = 0U;
}

/** Current time in us. Must be called at least every ~30 ms (it is:      */
/** the superloop iterates in the microsecond range).                     */
static inline uint32_t timestamp_us(void)
{
    uint32_t cnt = LL_TIM_GetCounter(TIM3);
    if (LL_TIM_IsActiveFlag_UPDATE(TIM3) != 0U)
    {
        LL_TIM_ClearFlag_UPDATE(TIM3);
        s_ts_high += 0x10000U;
        cnt = LL_TIM_GetCounter(TIM3);   /* re-read after rollover handling */
    }
    return s_ts_high + cnt;
}

/* --------------------------------------------------------------------------
 * Clock: HSI48 -> SYSCLK 48 MHz
 * ------------------------------------------------------------------------ */
static void system_clock_config(void)
{
    /* 1 wait state required above 24 MHz                                   */
    LL_FLASH_SetLatency(LL_FLASH_LATENCY_1);
    while (LL_FLASH_GetLatency() != LL_FLASH_LATENCY_1)
    {
    }
#if (SNIFF_FLASH_ACCEL != 0)
    /* fw 1.5: prefetch + instruction cache. With 1 WS and neither enabled,
     * every taken branch in the capture loop paid the flash latency.      */
    LL_FLASH_EnableInstCache();
    LL_FLASH_EnablePrefetch();
#endif

    /* HSI48 is the reset clock source; drop the default /4 divider         */
    LL_RCC_SetHSIDiv(LL_RCC_HSI_DIV_1);
    while (LL_RCC_GetHSIDiv() != LL_RCC_HSI_DIV_1)
    {
    }

    LL_RCC_SetAHBPrescaler(LL_RCC_HCLK_DIV_1);
    LL_RCC_SetAPB1Prescaler(LL_RCC_APB1_DIV_1);

    SystemCoreClockUpdate();
}

/* --------------------------------------------------------------------------
 * LED LD4 = PA5
 * ------------------------------------------------------------------------ */
static void led_init(void)
{
    LL_IOP_GRP1_EnableClock(LL_IOP_GRP1_PERIPH_GPIOA);
    LL_GPIO_SetPinMode(GPIOA, LL_GPIO_PIN_5, LL_GPIO_MODE_OUTPUT);
}

static inline void led_set(uint8_t on)
{
    if (on != 0U)
    {
        LL_GPIO_SetOutputPin(GPIOA, LL_GPIO_PIN_5);
    }
    else
    {
        LL_GPIO_ResetOutputPin(GPIOA, LL_GPIO_PIN_5);
    }
}

/* --------------------------------------------------------------------------
 * Timing trace pins (SNIFF_TRACE, see sniffer_config.h)
 * ------------------------------------------------------------------------ */
#if (SNIFF_MODE == SNIFF_MODE_BITBANG) && (SNIFF_TRACE != 0)
#define TRACE_LOOP_MASK   (1UL << 0)                 /* PA0 = A0          */
#define TRACE_BUSY_MASK   (1UL << 1)                 /* PA1 = A1          */
#define TRACE_BUSY_HI()   (GPIOA->BSRR = TRACE_BUSY_MASK)
#define TRACE_BUSY_LO()   (GPIOA->BRR  = TRACE_BUSY_MASK)
static void trace_init(void)
{
    LL_IOP_GRP1_EnableClock(LL_IOP_GRP1_PERIPH_GPIOA);
    GPIOA->BRR = TRACE_LOOP_MASK | TRACE_BUSY_MASK;
    LL_GPIO_SetPinMode(GPIOA, LL_GPIO_PIN_0, LL_GPIO_MODE_OUTPUT);
    LL_GPIO_SetPinMode(GPIOA, LL_GPIO_PIN_1, LL_GPIO_MODE_OUTPUT);
    LL_GPIO_SetPinSpeed(GPIOA, LL_GPIO_PIN_0, LL_GPIO_SPEED_FREQ_HIGH);
    LL_GPIO_SetPinSpeed(GPIOA, LL_GPIO_PIN_1, LL_GPIO_SPEED_FREQ_HIGH);
}
#define TRACE_ISR_HI()    (GPIOA->BSRR = TRACE_LOOP_MASK)
#define TRACE_ISR_LO()    (GPIOA->BRR  = TRACE_LOOP_MASK)
#else
#define TRACE_BUSY_HI()   ((void)0)
#define TRACE_BUSY_LO()   ((void)0)
#define TRACE_ISR_HI()    ((void)0)
#define TRACE_ISR_LO()    ((void)0)
#endif

/* --------------------------------------------------------------------------
 * Bit-bang mode pin setup: plain floating inputs, never driven
 * ------------------------------------------------------------------------ */
#if (SNIFF_MODE == SNIFF_MODE_BITBANG)
static void bitbang_pins_init(void)
{
    SNIFF_GPIO_CLK_EN();
    LL_GPIO_SetPinMode(SNIFF_GPIO_PORT, LL_GPIO_PIN_9,  LL_GPIO_MODE_INPUT);
    LL_GPIO_SetPinMode(SNIFF_GPIO_PORT, LL_GPIO_PIN_10, LL_GPIO_MODE_INPUT);
    LL_GPIO_SetPinPull(SNIFF_GPIO_PORT, LL_GPIO_PIN_9,  LL_GPIO_PULL_NO);
    LL_GPIO_SetPinPull(SNIFF_GPIO_PORT, LL_GPIO_PIN_10, LL_GPIO_PULL_NO);
}
#endif

#if SNIFF_EDGE_MODE
/* --------------------------------------------------------------------------
 * Edge capture (fw 1.6). EXTI lines 9 (SCL, PA9) and 10 (SDA, PA10), both
 * edges, on EXTI4_15 - the firmware's only interrupt. The ISR clears the
 * pending flags BEFORE reading the pins, so an edge that lands after the
 * read re-enters the ISR instead of being lost; it pushes only real line
 * changes. With SNIFF_TRACE >= 2, PA0 is high for the ISR's duration.
 * ------------------------------------------------------------------------ */
#define SNIFF_EXTI_MASK   ((1UL << SNIFF_SCL_PIN) | (1UL << SNIFF_SDA_PIN))
static edge_ring_t s_edges;
static uint8_t     s_isr_lines;        /* last line state pushed (ISR)     */
static uint32_t    s_edge_ovf_seen;    /* overflows already counted        */

static inline uint8_t edge_lines(uint32_t idr)
{
    return (uint8_t)(((idr >> SNIFF_SCL_PIN) & 1U) |
                     (((idr >> SNIFF_SDA_PIN) & 1U) << 1));
}

/* Not placed in RAM: tried 2026-10-05, only ~10 % faster (the time is in
 * the EXTI/TIM3 register accesses) and the linker warns on RWX.           */
void EXTI4_15_IRQHandler(void)
{
    TRACE_ISR_HI();
    EXTI->RPR1 = SNIFF_EXTI_MASK;      /* clear first, then sample          */
    EXTI->FPR1 = SNIFF_EXTI_MASK;
    const uint32_t idr = SNIFF_GPIO_PORT->IDR;
    const uint16_t t16 = (uint16_t)TIM3->CNT;
    const uint8_t  l   = edge_lines(idr);
    if (l != s_isr_lines)
    {
        s_isr_lines = l;
        (void)edge_ring_push(&s_edges, t16, l);
    }
    TRACE_ISR_LO();
}

static void edge_irq_init(void)
{
    LL_APB2_GRP1_EnableClock(LL_APB2_GRP1_PERIPH_SYSCFG);
    /* EXTICR3 holds lines 8..11, 8 bits each; 0 = port A                  */
    EXTI->EXTICR[2] &= ~((0xFFUL << ((SNIFF_SCL_PIN - 8U) * 8U)) |
                         (0xFFUL << ((SNIFF_SDA_PIN - 8U) * 8U)));
    EXTI->IMR1  &= ~SNIFF_EXTI_MASK;
    EXTI->RTSR1 |= SNIFF_EXTI_MASK;
    EXTI->FTSR1 |= SNIFF_EXTI_MASK;
    NVIC_SetPriority(EXTI4_15_IRQn, 0U);
    NVIC_EnableIRQ(EXTI4_15_IRQn);
}

/* off -> ring reset -> seed the current line state -> on                  */
static void edge_irq_enable(uint8_t on, uint32_t now_us)
{
    EXTI->IMR1 &= ~SNIFF_EXTI_MASK;
    if (on != 0U)
    {
        edge_ring_reset(&s_edges, now_us);
        s_edge_ovf_seen = 0U;
        EXTI->RPR1 = SNIFF_EXTI_MASK;
        EXTI->FPR1 = SNIFF_EXTI_MASK;
        s_isr_lines = edge_lines(SNIFF_GPIO_PORT->IDR);
        (void)edge_ring_push(&s_edges, (uint16_t)now_us, s_isr_lines);
        EXTI->IMR1 |= SNIFF_EXTI_MASK;
    }
}
#endif

/* --------------------------------------------------------------------------
 * Shared capture bookkeeping
 * ------------------------------------------------------------------------ */
static uint8_t       s_running;

#if (SNIFF_MODE == SNIFF_MODE_BITBANG)
/* [XREF: deferred-emit] Completed transactions are queued and encoded to
 * UART only while the bus is idle. Encoding + enqueueing inside the sample
 * path stalled sampling long enough to corrupt the phase after a repeated
 * START (field capture: restart reads decoded at 0x5C instead of 0x6B).
 * [XREF: zero-copy-ring] fw 1.2: the queue is the decoder's own ring, so a
 * completed transaction costs no copy at all. fw 1.1 still struct-copied
 * ~76 bytes here (byte-wise newlib-nano memcpy, roughly 20 us), which at
 * ~47 kHz lost the first SCL edge after every repeated START
 * ("working test 1.csv": Sr R 0x10 [00 01] logged as Sr W 0x21 [00 03]). */
#define BUS_IDLE_FLUSH_US     20U
/* Only SCL/SDA may wake the decoder: the rest of port A carries the UART
 * TX line and the LED, whose toggling would otherwise count as bus
 * activity and hold off the idle flush.                                    */
#define SNIFF_IDR_MASK        ((1UL << SNIFF_SCL_PIN) | (1UL << SNIFF_SDA_PIN))
static uint32_t      s_last_edge_us;   /* last bus line activity           */
#endif
static uint32_t      s_captured;
static uint32_t      s_errors;
static uint32_t      s_dropped;
#if (SNIFF_MODE == SNIFF_MODE_BITBANG)
static i2c_decoder_t s_dec;                 /* bit-bang decoder instance    */
#endif
static uint8_t       s_frame_buf[FRAME_MAX_ENCODED];

#if (SNIFF_MODE == SNIFF_MODE_BITBANG)
static uint32_t      s_txn_open_us;     /* when the current txn opened     */
static uint8_t       s_prev_in_txn;
static uint8_t       s_upkeep_pending;  /* an upkeep slot is being held off */
static uint32_t      s_deferred;        /* upkeep slots deferred (B30)      */
#endif

#if (SNIFF_MODE == SNIFF_MODE_BITBANG) && (SNIFF_DIAG != 0)
/* --------------------------------------------------------------------------
 * Sampler diagnostics (review B30/B31). TIM14 counts SYSCLK cycles.
 *   gap  : cycles between two consecutive samples while a txn is open
 *   high : cycles from the SCL-rise sample to the SCL-fall sample
 *   low  : cycles from the SCL-fall sample to the SCL-rise sample
 * Edge widths are only measured inside an open transaction (idle highs can
 * exceed the 1.365 ms TIM14 wrap); a stretch longer than 1.365 ms aliases.
 * A FRAMING-flagged phase records its own worst gap / narrowest high, which
 * tells "sampler stalled" (big gap) from "pulse narrower than the loop"
 * (small high) apart.
 * ------------------------------------------------------------------------ */
static struct
{
    uint16_t max_gap, min_high, min_low, frm_max_gap, frm_min_high;
    uint32_t gaps_2us, framing;
} s_diag;
static uint16_t s_tk_prev, s_tk_rise, s_tk_fall;
static uint8_t  s_have_rise, s_have_fall;
static uint16_t s_ph_max_gap, s_ph_min_high, s_ph_min_low;  /* open phase  */

static void diag_reset(void)
{
    s_diag.max_gap = 0U;      s_diag.min_high = 0xFFFFU; s_diag.min_low = 0xFFFFU;
    s_diag.frm_max_gap = 0U;  s_diag.frm_min_high = 0xFFFFU;
    s_diag.gaps_2us = 0U;     s_diag.framing = 0U;
    s_ph_max_gap = 0U;        s_ph_min_high = 0xFFFFU;   s_ph_min_low = 0xFFFFU;
    s_have_rise = 0U;         s_have_fall = 0U;
}

static void diag_init(void)
{
    LL_APB2_GRP1_EnableClock(LL_APB2_GRP1_PERIPH_TIM14);
    LL_TIM_SetPrescaler(TIM14, 0U);              /* SYSCLK ticks           */
    LL_TIM_SetAutoReload(TIM14, 0xFFFFU);
    LL_TIM_SetCounterMode(TIM14, LL_TIM_COUNTERMODE_UP);
    LL_TIM_GenerateEvent_UPDATE(TIM14);
    LL_TIM_EnableCounter(TIM14);
    diag_reset();
}

/* fold the phase that just closed into the totals                          */
static void diag_phase_end(uint8_t framing)
{
    if (s_ph_max_gap > s_diag.max_gap)    { s_diag.max_gap  = s_ph_max_gap;  }
    if (s_ph_min_high < s_diag.min_high)  { s_diag.min_high = s_ph_min_high; }
    if (s_ph_min_low < s_diag.min_low)    { s_diag.min_low  = s_ph_min_low;  }
    if (framing != 0U)
    {
        s_diag.framing++;
        if (s_ph_max_gap > s_diag.frm_max_gap)   { s_diag.frm_max_gap  = s_ph_max_gap;  }
        if (s_ph_min_high < s_diag.frm_min_high) { s_diag.frm_min_high = s_ph_min_high; }
    }
    s_ph_max_gap = 0U;
    s_ph_min_high = 0xFFFFU;
    s_ph_min_low = 0xFFFFU;
}
#endif

static void send_frame(uint32_t len)
{
    if (uart_stream_write(s_frame_buf, len) == 0U)
    {
        s_dropped++;
    }
}

static void send_status(void)
{
    status_info_t st;
    st.proto_ver = FRAME_PROTOCOL_VERSION;
    st.fw_major  = FW_VERSION_MAJOR;
    st.fw_minor  = FW_VERSION_MINOR;
    st.mode      = SNIFF_MODE;
    st.state     = (s_running != 0U) ? CAPTURE_STATE_RUNNING
                                     : CAPTURE_STATE_IDLE;
#if (SNIFF_MODE == SNIFF_MODE_MASTER)
    st.captured  = i2c_master_txn_count();
    st.errors    = i2c_master_error_count();
    st.dropped   = 0U;
    st.bus_hz    = 0U;                  /* master sets the clock; N/A       */
#else
    st.captured  = s_captured;
    st.errors    = s_errors;
    st.dropped   = s_dropped;
#if (SNIFF_MODE == SNIFF_MODE_BITBANG)
    st.bus_hz    = i2c_dec_bus_hz(&s_dec);
#else
    st.bus_hz    = smon_bus_hz();
#endif
#endif
    st.diag_valid = 0U;
#if (SNIFF_MODE == SNIFF_MODE_BITBANG) && (SNIFF_DIAG != 0)
    st.diag_valid        = 1U;
    st.diag_max_gap      = s_diag.max_gap;
    st.diag_min_high     = s_diag.min_high;
    st.diag_min_low      = s_diag.min_low;
    st.diag_gaps_2us     = s_diag.gaps_2us;
    st.diag_framing      = s_diag.framing;
    st.diag_frm_max_gap  = s_diag.frm_max_gap;
    st.diag_frm_min_high = s_diag.frm_min_high;
    st.diag_deferred     = s_deferred;
#endif
    send_frame(frame_encode_status(s_frame_buf, &st));
}

static void capture_start(void)
{
    s_running  = 1U;
    s_captured = 0U;
    s_errors   = 0U;
    s_dropped  = 0U;
#if (SNIFF_MODE == SNIFF_MODE_BITBANG)
#if SNIFF_EDGE_MODE
    edge_irq_enable(0U, 0U);
#endif
    i2c_dec_init(&s_dec);
    s_prev_in_txn = 0U;
    s_upkeep_pending = 0U;
    s_deferred = 0U;
#if (SNIFF_DIAG != 0)
    diag_reset();
#endif
#if SNIFF_EDGE_MODE
    edge_irq_enable(1U, timestamp_us());
#endif
#else
    smon_enable(1U);
#endif
    led_set(1U);
}

static void capture_stop(void)
{
    s_running = 0U;
#if SNIFF_EDGE_MODE
    edge_irq_enable(0U, 0U);
#endif
#if (SNIFF_MODE == SNIFF_MODE_SLAVE_MON)
    smon_enable(0U);
#endif
}

static void handle_command(uint8_t cmd, uint8_t arg)
{
    (void)arg;
#if (SNIFF_MODE == SNIFF_MODE_MASTER)
    /* Variable-length master commands are dispatched before this function
     * (they carry a payload, see the parser loop); START/STOP are
     * meaningless for a master and rejected per PROTOCOL.md.               */
    if (cmd == CMD_START || cmd == CMD_STOP)
    {
        send_frame(frame_encode_error(s_frame_buf, ERR_CODE_BAD_COMMAND, cmd));
        return;
    }
#endif
    switch (cmd)
    {
        case CMD_START:
            capture_start();
            send_status();
            break;

        case CMD_STOP:
            capture_stop();
            send_status();
            break;

        case CMD_STATUS_REQ:
            send_status();
            break;

        case CMD_PING:
            send_frame(frame_encode_hello(s_frame_buf, SNIFF_MODE));
            break;

        case CMD_RESET_COUNTS:
            s_captured = 0U;
            s_errors   = 0U;
            s_dropped  = 0U;
#if (SNIFF_MODE == SNIFF_MODE_BITBANG)
            s_deferred = 0U;
#if (SNIFF_DIAG != 0)
            diag_reset();
#endif
#endif
            send_status();
            break;

        default:
            send_frame(frame_encode_error(s_frame_buf,
                                          ERR_CODE_BAD_COMMAND, cmd));
            break;
    }
}

/* --------------------------------------------------------------------------
 * main
 * ------------------------------------------------------------------------ */
int main(void)
{
    cmd_parser_t parser;
    uint32_t     upkeep_div      = 0U;
    uint32_t     last_status_us  = 0U;
    uint32_t     last_blink_us   = 0U;
    uint8_t      led_state       = 0U;
#if (SNIFF_MODE == SNIFF_MODE_BITBANG) && !SNIFF_EDGE_MODE
    uint32_t     idr_prev        = 0xFFFFFFFFU;
#endif

    system_clock_config();
    timestamp_init();
#if (SNIFF_MODE == SNIFF_MODE_MASTER)
    i2c_master_init(timestamp_us);
#endif
    led_init();
    uart_stream_init();
    cmd_parser_init(&parser);

#if (SNIFF_MODE == SNIFF_MODE_BITBANG)
    bitbang_pins_init();
#if (SNIFF_TRACE != 0)
    trace_init();
#endif
#if SNIFF_EDGE_MODE
    edge_irq_init();
#endif
#if (SNIFF_DIAG != 0)
    diag_init();
#endif
#elif (SNIFF_MODE == SNIFF_MODE_SLAVE_MON)
    smon_init();
#endif  /* master: i2c_master_init() above owns the pins */

    s_running = 0U;

    /* Boot banner so the host can auto-detect the device                   */
    send_frame(frame_encode_hello(s_frame_buf, SNIFF_MODE));
    uart_stream_flush();

    for (;;)
    {
        const uint32_t now_us = timestamp_us();

        /* ---------------- hot path: capture ---------------------------- */
        if (s_running != 0U)
        {
#if SNIFF_EDGE_MODE
            /* fw 1.6: the EXTI ISR has already sampled every edge; decode
             * one per pass. now_us was read before the pop, so an empty
             * ring may re-anchor the 16-bit edge time base (edge_ring.h). */
            uint32_t et;
            uint8_t  el;
            if (edge_ring_pop(&s_edges, &et, &el) != 0U)
            {
                s_last_edge_us = et;
                const i2c_dec_event_t evt =
                    i2c_dec_sample(&s_dec, (uint8_t)(el & EDGE_SCL),
                                   (uint8_t)(el >> 1), et);
                if (evt == I2C_DEC_EVT_TXN)
                {
                    s_captured++;
                }
                else if (evt == I2C_DEC_EVT_DROPPED)
                {
                    s_captured++;
                    s_dropped++;
                }
                else if (evt == I2C_DEC_EVT_BUS_ERROR)
                {
                    s_errors++;            /* missed START                  */
                }
                if ((s_dec.in_txn != 0U) && (s_prev_in_txn == 0U))
                {
                    s_txn_open_us = et;
                }
                s_prev_in_txn = s_dec.in_txn;
            }
            else
            {
                edge_ring_idle_sync(&s_edges, now_us);
            }
            if (s_edges.overflow != s_edge_ovf_seen)
            {
                s_errors += s_edges.overflow - s_edge_ovf_seen;  /* edges lost */
                s_edge_ovf_seen = s_edges.overflow;
            }
#elif (SNIFF_MODE == SNIFF_MODE_BITBANG)
            const uint32_t idr = SNIFF_GPIO_PORT->IDR & SNIFF_IDR_MASK;
#if (SNIFF_TRACE >= 2)
            GPIOA->ODR ^= TRACE_LOOP_MASK;               /* loop heartbeat  */
#endif
#if (SNIFF_DIAG != 0)
            const uint16_t tk = (uint16_t)TIM14->CNT;     /* right after IDR */
            if (s_dec.in_txn != 0U)
            {
                const uint16_t g = (uint16_t)(tk - s_tk_prev);
                if (g > s_ph_max_gap) { s_ph_max_gap = g; }
                if (g > (2U * DIAG_TICKS_PER_US)) { s_diag.gaps_2us++; }
            }
            else
            {
                s_have_rise = 0U;      /* widths only inside a transaction */
                s_have_fall = 0U;
            }
            s_tk_prev = tk;
#endif
            if (idr != idr_prev)   /* decode only on line activity          */
            {
#if (SNIFF_DIAG != 0)
                if (((idr ^ idr_prev) & (1UL << SNIFF_SCL_PIN)) != 0U)
                {
                    if ((idr & (1UL << SNIFF_SCL_PIN)) != 0U)   /* SCL rose */
                    {
                        if (s_have_fall)
                        {
                            const uint16_t w = (uint16_t)(tk - s_tk_fall);
                            if (w < s_ph_min_low) { s_ph_min_low = w; }
                        }
                        s_tk_rise = tk;
                        s_have_rise = 1U;
                    }
                    else                                         /* fell     */
                    {
                        if (s_have_rise)
                        {
                            const uint16_t w = (uint16_t)(tk - s_tk_rise);
                            if (w < s_ph_min_high) { s_ph_min_high = w; }
                        }
                        s_tk_fall = tk;
                        s_have_fall = 1U;
                    }
                }
#endif
                idr_prev = idr;
                s_last_edge_us = now_us;
                const uint8_t scl = (uint8_t)((idr >> SNIFF_SCL_PIN) & 1U);
                const uint8_t sda = (uint8_t)((idr >> SNIFF_SDA_PIN) & 1U);
                const i2c_dec_event_t evt =
                    i2c_dec_sample(&s_dec, scl, sda, now_us);
                /* [XREF: zero-copy-ring] counters only - the record is     */
                /* already queued in the decoder's ring; keep sampling      */
                if (evt == I2C_DEC_EVT_TXN)
                {
                    s_captured++;
#if (SNIFF_DIAG != 0)
                    /* the phase just closed is the newest ring record       */
                    diag_phase_end(s_dec.ring[(s_dec.head + I2C_DEC_RING_DEPTH - 1U)
                                              % I2C_DEC_RING_DEPTH].framing);
#endif
                }
                else if (evt == I2C_DEC_EVT_DROPPED)
                {
                    s_captured++;
                    s_dropped++;
                }
                else if (evt == I2C_DEC_EVT_BUS_ERROR)
                {
                    s_errors++;            /* missed START                  */
                }
                if ((s_dec.in_txn != 0U) && (s_prev_in_txn == 0U))
                {
                    s_txn_open_us = now_us;
                }
                s_prev_in_txn = s_dec.in_txn;
            }
#endif
#if (SNIFF_MODE == SNIFF_MODE_BITBANG)
            /* [XREF: deferred-emit] flush queued frames only BETWEEN
             * transactions - never while one is open, where a stall slips
             * bits. Normally wait for BUS_IDLE_FLUSH_US of quiet; under
             * ring pressure, flush at once after a STOP. One frame per
             * iteration so a late-arriving START is picked up quickly.     */
            if ((i2c_dec_pending(&s_dec) != 0U) && (s_dec.in_txn == 0U) &&
                ((i2c_dec_pending(&s_dec) >= (I2C_DEC_RING_DEPTH / 2U)) ||
                 ((now_us - s_last_edge_us) >= BUS_IDLE_FLUSH_US)))
            {
                TRACE_BUSY_HI();
                const i2c_txn_t *t = i2c_dec_peek(&s_dec);
                if (t->framing != 0U)
                {
                    s_errors++;            /* bit-slipped phase             */
                }
                send_frame(frame_encode_txn(s_frame_buf, t));
                i2c_dec_pop(&s_dec);
                TRACE_BUSY_LO();
            }
#elif (SNIFF_MODE == SNIFF_MODE_SLAVE_MON)
            i2c_txn_t txn;
            if (smon_poll(&txn, now_us) != 0U)
            {
                s_captured++;
                send_frame(frame_encode_txn(s_frame_buf, &txn));
            }
#endif  /* master mode: nothing to poll; work happens in command dispatch */
        }

        /* ---------------- upkeep every 64 iterations -------------------- */
        upkeep_div++;
#if (SNIFF_MODE == SNIFF_MODE_BITBANG) && (SNIFF_DEFER_UPKEEP != 0)
        /* [B30] hold the upkeep slot while a transaction is open: retry on
         * every iteration until the bus closes it (or the safety timeout).  */
        if (((upkeep_div & 0x3FU) == 0U) && (s_running != 0U) &&
            (s_dec.in_txn != 0U) && ((now_us - s_txn_open_us) < UPKEEP_MAX_DEFER_US))
        {
            if (s_upkeep_pending == 0U)
            {
                s_upkeep_pending = 1U;
                s_deferred++;
            }
            upkeep_div--;
        }
        else
#endif
        if ((upkeep_div & 0x3FU) == 0U)
        {
            uint8_t rx;
            TRACE_BUSY_HI();
#if (SNIFF_MODE == SNIFF_MODE_BITBANG)
            s_upkeep_pending = 0U;
#endif

            uart_stream_poll();

            while (uart_stream_read_byte(&rx) != 0U)
            {
                const cmd_event_t ce = cmd_parser_feed(&parser, rx);
                if (ce == CMD_EVT_COMMAND)
                {
#if (SNIFF_MODE == SNIFF_MODE_MASTER)
                    if (parser.cmd >= CMD_VAR_MIN)
                    {
                        i2c_master_exec(parser.cmd, parser.payload,
                                        parser.len);
                        if (parser.cmd == CMD_SET_BUS_SPEED)
                        {
                            send_status();     /* speed change ack          */
                        }
                    }
                    else
#endif
                    {
                        handle_command(parser.cmd, parser.arg);
                    }
                }
                else if (ce == CMD_EVT_BAD_CRC)
                {
                    send_frame(frame_encode_error(s_frame_buf,
                                                  ERR_CODE_BAD_COMMAND, 0xFFU));
                }
            }

            /* 1 Hz status while running                                    */
            if ((s_running != 0U) &&
                ((now_us - last_status_us) >= STATUS_PERIOD_US))
            {
                last_status_us = now_us;
                send_status();
            }

            /* idle heartbeat at 2 Hz                                       */
            if (s_running == 0U)
            {
                if ((now_us - last_blink_us) >= 250000U)
                {
                    last_blink_us = now_us;
                    led_state ^= 1U;
                    led_set(led_state);
                }
            }
            TRACE_BUSY_LO();
        }
    }
}
