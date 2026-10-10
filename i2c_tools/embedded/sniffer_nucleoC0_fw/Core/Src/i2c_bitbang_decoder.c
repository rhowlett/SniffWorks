/**
 * [v0.1]
 ******************************************************************************
 * @file    i2c_bitbang_decoder.c
 * @brief   Pure, platform-independent I2C bus decoder (see header).
 *
 * State machine summary
 * ---------------------
 *   SDA falling while SCL high  -> START (or repeated START inside a txn)
 *   SDA rising  while SCL high  -> STOP
 *   SCL rising                  -> sample one data bit (or the ACK bit)
 *
 * A byte is 8 data bits MSB-first followed by 1 ACK bit (SDA low = ACK).
 * The first byte after any START is the address byte: 7-bit address + R/W.
 *
 * Kept free of hardware access and libc so it can be unit-tested on the
 * host and inlined into the target's tight polling loop.
 ******************************************************************************
 */
#include "i2c_bitbang_decoder.h"

/* --------------------------------------------------------------------------
 * small helpers
 * ------------------------------------------------------------------------ */
static inline void txn_reset(i2c_txn_t *t)
{
    t->t_us     = 0U;
    t->addr7    = 0U;
    t->dir_read = 0U;
    t->nak      = 0U;
    t->restart  = 0U;
    t->stop     = 0U;
    t->overflow = 0U;
    t->timeout  = 0U;
    t->framing  = 0U;
    t->len      = 0U;
    t->scl_sum_us = 0U;
    t->scl_cnt    = 0U;
}

/* Per-phase SCL accumulator reset (at every START and repeated START).     */
static inline void scl_meas_reset(i2c_decoder_t *d)
{
    d->have_rise  = 0U;
    d->per_cnt    = 0U;
    d->per_min_us = 0U;
    d->per_sum_us = 0U;
}

/* Accept one rise-to-rise period. Gate: p <= 1.5 * shortest-so-far. When a
 * new shortest period arrives that is more than 1.5x shorter than the old
 * one, every period accepted so far lies outside the new gate, so the
 * accumulator restarts from this period.                                    */
static inline void scl_meas_period(i2c_decoder_t *d, uint32_t p)
{
    if (p == 0U)
    {
        return;                     /* two rises in one tick: glitch         */
    }
    /* shifts + adds only: runs on every SCL rise                           */
    if ((d->per_min_us == 0U) || (p < d->per_min_us))
    {
        if ((d->per_min_us != 0U) && (((p << 1) + p) < (d->per_min_us << 1)))
        {
            d->per_cnt    = 0U;
            d->per_sum_us = 0U;
        }
        d->per_min_us = p;
    }
    if (((p << 1) <= ((d->per_min_us << 1) + d->per_min_us))
        && (d->per_cnt < 4000U))
    {
        d->per_sum_us += p;         /* cnt cap keeps 1e6*cnt inside u32      */
        d->per_cnt++;
    }
}



void i2c_dec_init(i2c_decoder_t *d)
{
    d->prev_scl          = 1U;    /* idle bus is high/high                  */
    d->prev_sda          = 1U;
    d->bit_count         = 0U;
    d->shift             = 0U;
    d->phase             = I2C_DEC_IDLE;
    d->in_txn            = 0U;
    d->last_scl_rise_us  = 0U;
    d->last_sum_us       = 0U;
    d->last_cnt          = 0U;
    scl_meas_reset(d);
    d->txn_count         = 0U;
    d->err_count         = 0U;
    d->drop_count        = 0U;
    d->head              = 0U;
    d->tail              = 0U;
    d->count             = 0U;
    d->lost              = 0U;
    d->cur               = &d->ring[0];
    txn_reset(d->cur);
}

void i2c_dec_pop(i2c_decoder_t *d)
{
    if (d->count != 0U)
    {
        d->tail = (uint8_t)((d->tail + 1U >= I2C_DEC_RING_DEPTH)
                            ? 0U : (d->tail + 1U));
        d->count--;
    }
}

uint32_t i2c_dec_bus_hz(const i2c_decoder_t *d)
{
    return i2c_scl_hz(d->last_sum_us, d->last_cnt);   /* 1 Hz STATUS path */
}

/* --------------------------------------------------------------------------
 * Close the currently-assembling transaction.
 * closed_by_stop: 1 = STOP condition, 0 = repeated START
 *
 * [XREF: zero-copy-ring] O(1): the record already lives in ring[head], so
 * closing it just advances head. This runs at every repeated START, the
 * one moment the next phase's first SCL edge is only ~half a bit away, so
 * it must never copy the record.
 *
 * Framing check: on a well-framed bus the SCL rise that sets up a STOP or
 * a repeated START is the only clock after the last ACK cell, so bit_count
 * is exactly 1 here. Any other value means an SCL edge was lost (or a
 * glitch added one) and every byte of this phase is bit-slipped.
 * ------------------------------------------------------------------------ */
static inline i2c_dec_event_t finish_txn(i2c_decoder_t *d, uint8_t closed_by_stop)
{
    i2c_txn_t *t = d->cur;

    t->stop   = closed_by_stop;
    t->scl_sum_us = d->per_sum_us;  /* raw copy: no division here            */
    t->scl_cnt    = d->per_cnt;
    if (d->per_cnt >= I2C_DEC_SCL_MIN_PERIODS)
    {
        d->last_sum_us = d->per_sum_us;
        d->last_cnt    = d->per_cnt;
    }
    if (d->bit_count != 1U)
    {
        t->framing = 1U;
        d->err_count++;
    }
    d->txn_count++;

    if (d->count >= (uint8_t)(I2C_DEC_RING_DEPTH - 1U))
    {
        d->drop_count++;          /* ring full: slot is reused as-is       */
        return I2C_DEC_EVT_DROPPED;
    }
    d->head = (uint8_t)((d->head + 1U >= I2C_DEC_RING_DEPTH)
                        ? 0U : (d->head + 1U));
    d->count++;
    d->cur = &d->ring[d->head];
    return I2C_DEC_EVT_TXN;
}

i2c_dec_event_t i2c_dec_sample(i2c_decoder_t *d,
                               uint8_t scl, uint8_t sda, uint32_t t_us)
{
    i2c_dec_event_t evt = I2C_DEC_EVT_NONE;

    const uint8_t scl_rose  = (uint8_t)(scl & (uint8_t)!d->prev_scl);
    const uint8_t scl_fell  = (uint8_t)((uint8_t)!scl & d->prev_scl);
    const uint8_t sda_fell  = (uint8_t)((uint8_t)!sda & d->prev_sda);
    const uint8_t sda_rose  = (uint8_t)(sda & (uint8_t)!d->prev_sda);

    /* ---- START / repeated START: SDA falls while SCL is high ---------- */
    if (sda_fell && scl && d->prev_scl)
    {
        if (d->in_txn)
        {
            /* Repeated START: close the running record without STOP.      */
            evt = finish_txn(d, 0U);
            txn_reset(d->cur);
            d->cur->restart = 1U;
        }
        else
        {
            txn_reset(d->cur);
        }
        d->cur->t_us = t_us;
        scl_meas_reset(d);          /* each phase is measured on its own     */
        d->in_txn    = 1U;
        d->lost      = 0U;
        d->phase    = I2C_DEC_ADDR;
        d->bit_count = 0U;
        d->shift     = 0U;
    }
    /* ---- STOP: SDA rises while SCL is high ----------------------------- */
    else if (sda_rose && scl && d->prev_scl)
    {
        if (d->in_txn)
        {
            evt = finish_txn(d, 1U);
        }
        d->in_txn = 0U;
        d->phase  = I2C_DEC_IDLE;
        d->lost   = 0U;
    }
    /* ---- SCL clocking with no open transaction: START was missed ------- */
    else if (scl_fell && !d->in_txn)
    {
        if (!d->lost)
        {
            d->lost = 1U;           /* one report per lost transaction     */
            d->err_count++;
            evt = I2C_DEC_EVT_BUS_ERROR;
        }
    }
    /* ---- data / ACK bit: sample SDA on SCL rising edge ----------------- */
    else if (scl_rose && d->in_txn)
    {
        /* SCL measurement from the rise-to-rise interval (wrap-safe)       */
        if (d->have_rise != 0U)
        {
            scl_meas_period(d, t_us - d->last_scl_rise_us);
        }
        d->last_scl_rise_us = t_us;
        d->have_rise        = 1U;

        if (d->bit_count < 8U)
        {
            d->shift = (uint8_t)((d->shift << 1) | (sda & 1U));
            d->bit_count++;
        }
        else
        {
            /* 9th clock: ACK (SDA low) / NAK (SDA high)                    */
            const uint8_t is_nak = (uint8_t)(sda & 1U);

            if (d->phase == I2C_DEC_ADDR)
            {
                d->cur->addr7    = (uint8_t)(d->shift >> 1);
                d->cur->dir_read = (uint8_t)(d->shift & 1U);
                d->cur->nak      = is_nak;   /* address NAK                  */
                d->phase         = I2C_DEC_DATA;
            }
            else
            {
                if (d->cur->len < TXN_MAX_DATA)
                {
                    d->cur->data[d->cur->len] = d->shift;
                    d->cur->len++;
                }
                else
                {
                    d->cur->overflow = 1U;
                }
                /* Track the FINAL ACK state: a master NAK terminating a    */
                /* read is normal protocol, but the Python model records    */
                /* the last NAK seen, so mirror that behaviour.             */
                d->cur->nak = is_nak;
            }
            d->bit_count = 0U;
            d->shift     = 0U;
        }
    }
    else
    {
        /* level hold or SDA change while SCL low: normal data transitions */
    }

    d->prev_scl = scl;
    d->prev_sda = sda;
    return evt;
}
