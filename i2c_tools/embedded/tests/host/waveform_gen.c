/**
 * [v0.1]
 * waveform_gen.c - I2C waveform synthesis for decoder unit tests.
 *
 * Timing model: each bit cell is 4 quarter-bits.
 *   quarter 0: SCL low,  SDA transitions to the bit value
 *   quarter 1: SCL high  (bit stable - decoder samples here)
 *   quarter 2: SCL high
 *   quarter 3: SCL low
 * START/STOP manipulate SDA during an SCL-high window per the I2C spec.
 */
#include "waveform_gen.h"
#include <assert.h>

static uint8_t cur_scl = 1U;
static uint8_t cur_sda = 1U;

static void emit(wg_stream_t *s, uint8_t scl, uint8_t sda, uint32_t reps)
{
    for (uint32_t r = 0; r < reps; r++)
    {
        assert(s->n < WG_MAX_SAMPLES && "waveform buffer overflow");
        s->scl[s->n]  = scl;
        s->sda[s->n]  = sda;
        s->t_us[s->n] = (uint32_t)(((uint64_t)s->n * s->ns_per_sample) / 1000U);
        s->n++;
    }
    cur_scl = scl;
    cur_sda = sda;
}

void wg_init(wg_stream_t *s, uint32_t samples_per_quarter_bit,
             uint32_t us_per_sample)
{
    s->n = 0;
    s->samples_per_quarter_bit = samples_per_quarter_bit;
    s->us_per_sample = us_per_sample;
    s->ns_per_sample = us_per_sample * 1000U;   /* identical timestamps     */
    s->stretch_bit = -1;
    s->stretch_samples = 0U;
    cur_scl = 1U;
    cur_sda = 1U;
    emit(s, 1U, 1U, samples_per_quarter_bit);   /* settle idle */
}

void wg_init_ns(wg_stream_t *s, uint32_t samples_per_quarter_bit,
                uint32_t ns_per_sample)
{
    wg_init(s, samples_per_quarter_bit, 0U);
    s->n = 0;                                    /* redo settle with ns step */
    s->ns_per_sample = ns_per_sample;
    emit(s, 1U, 1U, samples_per_quarter_bit);
}

void wg_stretch_next_byte(wg_stream_t *s, uint32_t bit_index, uint32_t samples)
{
    s->stretch_bit = (int32_t)bit_index;
    s->stretch_samples = samples;
}

/* SCL held low (current SDA kept) if this bit cell is the stretched one.   */
static void maybe_stretch(wg_stream_t *s, int32_t cell)
{
    if (s->stretch_bit == cell)
    {
        emit(s, 0U, cur_sda, s->stretch_samples);
        s->stretch_bit = -1;
    }
}

void wg_idle(wg_stream_t *s, uint32_t quarter_bits)
{
    emit(s, cur_scl, cur_sda, quarter_bits * s->samples_per_quarter_bit);
}

void wg_start(wg_stream_t *s)
{
    const uint32_t q = s->samples_per_quarter_bit;
    /* ensure SDA high while SCL high, then drop SDA (START), then SCL low  */
    if (cur_scl == 0U)
    {
        /* repeated START from a mid-transfer state: raise SDA first, then  */
        /* SCL, then perform the START                                      */
        emit(s, 0U, 1U, q);
        emit(s, 1U, 1U, q);
    }
    else if (cur_sda == 0U)
    {
        emit(s, 1U, 1U, q);
    }
    emit(s, 1U, 1U, q);
    emit(s, 1U, 0U, q);      /* SDA falls while SCL high -> START           */
    emit(s, 0U, 0U, q);      /* SCL low, ready for first bit                */
}

void wg_stop(wg_stream_t *s)
{
    const uint32_t q = s->samples_per_quarter_bit;
    emit(s, 0U, 0U, q);      /* SDA low while SCL low                       */
    emit(s, 1U, 0U, q);      /* SCL high                                    */
    emit(s, 1U, 1U, q);      /* SDA rises while SCL high -> STOP            */
}

void wg_byte(wg_stream_t *s, uint8_t byte, uint8_t nak)
{
    const uint32_t q = s->samples_per_quarter_bit;
    for (int b = 7; b >= 0; b--)
    {
        const uint8_t bit = (uint8_t)((byte >> b) & 1U);
        emit(s, 0U, bit, q);        /* setup while SCL low                  */
        maybe_stretch(s, 7 - b);    /* slave holds SCL low (clock stretch)  */
        emit(s, 1U, bit, 2U * q);   /* SCL high - sample window             */
        emit(s, 0U, bit, q);        /* SCL back low                         */
    }
    /* ACK/NAK cell: ACK = SDA low, NAK = SDA high                          */
    const uint8_t ack_sda = (nak != 0U) ? 1U : 0U;
    emit(s, 0U, ack_sda, q);
    maybe_stretch(s, 8);
    emit(s, 1U, ack_sda, 2U * q);
    emit(s, 0U, ack_sda, q);
}

void wg_txn(wg_stream_t *s, uint8_t addr7, uint8_t dir_read,
            const uint8_t *data, size_t len,
            uint8_t addr_nak, uint8_t final_nak, uint8_t send_stop)
{
    wg_start(s);
    wg_byte(s, (uint8_t)((addr7 << 1) | (dir_read & 1U)), addr_nak);
    if (addr_nak == 0U)
    {
        for (size_t i = 0; i < len; i++)
        {
            const uint8_t is_last = (i + 1U == len);
            wg_byte(s, data[i], (uint8_t)(is_last && final_nak));
        }
    }
    if (send_stop)
    {
        wg_stop(s);
    }
}
