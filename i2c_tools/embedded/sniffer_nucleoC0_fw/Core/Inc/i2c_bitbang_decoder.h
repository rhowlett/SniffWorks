/**
 * [v0.1]
 ******************************************************************************
 * @file    i2c_bitbang_decoder.h
 * @brief   Pure, platform-independent I2C bus decoder.
 *
 *          Consumes a stream of (SCL, SDA) line samples and produces
 *          transaction events. Contains NO hardware access so the exact same
 *          code runs on the STM32 target and inside host-side unit tests
 *          (see embedded/tests/host/).
 *
 *          Transaction model mirrors core/i2c_controller.py::I2CTransaction
 *          on the Python side:
 *            - each address phase is one transaction record
 *            - a repeated START closes the previous record (stop=0) and opens
 *              a new one flagged restart=1
 *
 *          [XREF: zero-copy-ring] Records are assembled IN PLACE in a ring
 *          owned by the decoder; closing one only advances an index. The
 *          old design copied the ~76-byte record twice at every repeated
 *          START (txn -> out -> caller's ring, via newlib-nano's byte-wise
 *          memcpy), stalling the sampler long enough to lose the first SCL
 *          edge of the following phase (field capture "working test 1":
 *          Sr R 0x10 [00 01] decoded as Sr W 0x21 [00 03]).
 ******************************************************************************
 */
#ifndef I2C_BITBANG_DECODER_H
#define I2C_BITBANG_DECODER_H

#include <stdint.h>
#include "sniffer_config.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ------------------------------------------------------------------------ */
/* Transaction record                                                        */
/* ------------------------------------------------------------------------ */
typedef struct
{
    uint32_t t_us;                  /* timestamp of the START, microseconds  */
    uint8_t  addr7;                 /* 7-bit address                         */
    uint8_t  dir_read;              /* 0 = write, 1 = read                   */
    uint8_t  nak;                   /* 1 if address or final byte was NAKed  */
    uint8_t  restart;               /* 1 if opened by a repeated START       */
    uint8_t  stop;                  /* 1 if closed by STOP (0 = by restart)  */
    uint8_t  overflow;              /* 1 if data[] was truncated             */
    uint8_t  timeout;               /* 1 if a master transfer timed out      */
    uint8_t  framing;               /* 1 if the phase closed off a bit       */
                                    /* boundary: an SCL edge was lost or     */
                                    /* gained, so the bytes are bit-slipped  */
    uint8_t  len;                   /* valid bytes in data[]                 */
    uint8_t  data[TXN_MAX_DATA];
    /* SCL measurement of this phase, stored raw so no division runs in    */
    /* the sampling path (finish_txn is on the repeated-START critical     */
    /* path, ~half a bit before the next edge; the M0+ has no divider).    */
    /* Read it with i2c_txn_scl_hz(). Both 0 = not measured (slave-monitor */
    /* or master mode).                                                    */
    uint32_t scl_sum_us;            /* sum of accepted SCL periods (us)      */
    uint16_t scl_cnt;               /* number of accepted periods            */
} i2c_txn_t;

/* ------------------------------------------------------------------------ */
/* Decoder events returned by i2c_dec_sample()                               */
/* ------------------------------------------------------------------------ */
typedef enum
{
    I2C_DEC_EVT_NONE = 0,           /* nothing to report                     */
    I2C_DEC_EVT_TXN,                /* a transaction completed and is queued */
                                    /* (i2c_dec_peek / i2c_dec_pop)          */
    I2C_DEC_EVT_DROPPED,            /* a transaction completed but the ring  */
                                    /* was full: it was discarded            */
    I2C_DEC_EVT_BUS_ERROR           /* framing anomaly (lost arbitration,    */
                                    /* glitch, sample-rate underrun...)      */
} i2c_dec_event_t;

/* ------------------------------------------------------------------------ */
/* Internal decoder state - treat as opaque                                  */
/* ------------------------------------------------------------------------ */
typedef enum
{
    I2C_DEC_IDLE = 0,               /* waiting for START                     */
    I2C_DEC_ADDR,                   /* clocking in address byte              */
    I2C_DEC_DATA,                   /* clocking in data bytes                */
} i2c_dec_phase_t;

typedef struct
{
    /* line state tracking */
    uint8_t  prev_scl;
    uint8_t  prev_sda;

    /* bit assembly */
    uint8_t  bit_count;             /* 0..8 (9th clock = ACK)                */
    uint8_t  shift;

    i2c_dec_phase_t phase;
    uint8_t  in_txn;                /* between START and STOP                */

    /* [XREF: zero-copy-ring] ring[head] (== *cur) is the record being    */
    /* assembled; ring[tail .. head) hold count completed records.          */
    i2c_txn_t  ring[I2C_DEC_RING_DEPTH];
    i2c_txn_t *cur;
    uint8_t    head;
    uint8_t    tail;
    uint8_t    count;
    uint8_t    lost;                /* SCL activity seen outside a txn       */
                                    /* (missed START) - reported once        */

    /* SCL measurement, per address phase (reset at every START / Sr).      */
    /* Mean of the rise-to-rise periods no longer than 1.5x the shortest    */
    /* one, so clock-stretched and inter-byte-stretched bits are excluded;  */
    /* averaging ~8 periods per byte resolves well below the 1 us tick.     */
    uint32_t last_scl_rise_us;
    uint8_t  have_rise;             /* last_scl_rise_us valid in this phase  */
    uint16_t per_cnt;               /* periods accumulated                   */
    uint32_t per_min_us;            /* shortest period this phase (0 = none) */
    uint32_t per_sum_us;            /* sum of accepted periods               */
    uint32_t last_sum_us;           /* raw measurement of the last phase     */
    uint16_t last_cnt;              /* that had enough periods               */

    /* counters */
    uint32_t txn_count;
    uint32_t err_count;             /* framing errors + missed STARTs        */
    uint32_t drop_count;            /* records discarded, ring full          */
} i2c_decoder_t;

/* ------------------------------------------------------------------------ */
/* API                                                                       */
/* ------------------------------------------------------------------------ */

/** Reset the decoder to IDLE (call once before use). */
void i2c_dec_init(i2c_decoder_t *d);

/**
 * Feed one line sample.
 * @param scl   sampled SCL level (0/1)
 * @param sda   sampled SDA level (0/1)
 * @param t_us  timestamp of this sample in microseconds (free-running)
 * @return I2C_DEC_EVT_TXN when a completed transaction was queued (read it
 *         with i2c_dec_peek), I2C_DEC_EVT_DROPPED when one completed but the
 *         ring was full, I2C_DEC_EVT_BUS_ERROR on a missed START.
 *
 * Call as fast as possible; the decoder is edge-driven and tolerates
 * repeated identical samples at any rate.
 */
i2c_dec_event_t i2c_dec_sample(i2c_decoder_t *d,
                               uint8_t scl, uint8_t sda, uint32_t t_us);

/** Oldest completed transaction, or 0 (NULL) when none is queued. The
 *  pointer stays valid until i2c_dec_pop(). */
static inline const i2c_txn_t *i2c_dec_peek(const i2c_decoder_t *d)
{
    return (d->count != 0U) ? &d->ring[d->tail] : (const i2c_txn_t *)0;
}

/** Release the record returned by i2c_dec_peek(). No-op when empty. */
void i2c_dec_pop(i2c_decoder_t *d);

/** Number of completed transactions waiting to be read. */
static inline uint8_t i2c_dec_pending(const i2c_decoder_t *d)
{
    return d->count;
}

/** Rounded SCL frequency in Hz from a raw (sum, count) measurement; 0 when
 *  fewer than I2C_DEC_SCL_MIN_PERIODS periods. Divides: call it from the
 *  main loop / frame encoder, never from the sampling path. */
static inline uint32_t i2c_scl_hz(uint32_t sum_us, uint16_t cnt)
{
    if ((cnt < I2C_DEC_SCL_MIN_PERIODS) || (sum_us == 0U))
    {
        return 0U;
    }
    return ((1000000U * (uint32_t)cnt) + (sum_us / 2U)) / sum_us;
}

/** Measured SCL of one phase in Hz (0 = not measured). */
static inline uint32_t i2c_txn_scl_hz(const i2c_txn_t *t)
{
    return i2c_scl_hz(t->scl_sum_us, t->scl_cnt);
}

/** SCL frequency in Hz of the most recent phase that could be measured
 *  (0 = none yet). Follows speed changes: it is not a sticky minimum. */
uint32_t i2c_dec_bus_hz(const i2c_decoder_t *d);

#ifdef __cplusplus
}
#endif

#endif /* I2C_BITBANG_DECODER_H */
