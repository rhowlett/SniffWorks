/**
 * [v0.1]
 * waveform_gen.h - synthesize I2C SCL/SDA sample streams for host-side
 * testing of the bit-bang decoder. Emulates a master (and slave ACKs)
 * driving an open-drain bus, sampled at a fixed rate.
 */
#ifndef WAVEFORM_GEN_H
#define WAVEFORM_GEN_H

#include <stdint.h>
#include <stddef.h>

#define WG_MAX_SAMPLES  200000

typedef struct
{
    uint8_t  scl[WG_MAX_SAMPLES];
    uint8_t  sda[WG_MAX_SAMPLES];
    uint32_t t_us[WG_MAX_SAMPLES];
    size_t   n;
    /* generation params */
    uint32_t samples_per_quarter_bit;   /* sample-rate / (4 * bus clock);   */
                                        /* may be changed between calls to  */
                                        /* step the bus speed mid-stream    */
    uint32_t us_per_sample;             /* timestamp step (wg_init only)    */
    uint32_t ns_per_sample;             /* sample period; t_us is floor()ed */
                                        /* to 1 us like the firmware timer  */
    int32_t  stretch_bit;               /* next wg_byte: bit cell 0..8 held */
    uint32_t stretch_samples;           /* SCL-low for stretch_samples      */
                                        /* (-1 = no stretch)                */
} wg_stream_t;

/* Integer-microsecond sample step (all original tests).                    */
void wg_init(wg_stream_t *s, uint32_t samples_per_quarter_bit,
             uint32_t us_per_sample);
/* Nanosecond sample step: models a fast sampler whose timestamps come from
 * a 1 MHz timer, so bit periods that are not whole microseconds (400 kHz =
 * 2.5 us) quantise exactly as they do on the target.                       */
void wg_init_ns(wg_stream_t *s, uint32_t samples_per_quarter_bit,
                uint32_t ns_per_sample);
/* Clock-stretch the NEXT wg_byte: hold SCL low for `samples` extra samples
 * in bit cell `bit_index` (0 = MSB .. 7 = LSB, 8 = ACK cell), as a slave
 * stretching mid-byte would. Between-byte stretch = wg_idle() after a byte. */
void wg_stretch_next_byte(wg_stream_t *s, uint32_t bit_index, uint32_t samples);

/* Primitives (bus idles high/high) */
void wg_idle(wg_stream_t *s, uint32_t quarter_bits);
void wg_start(wg_stream_t *s);            /* also usable as repeated START  */
void wg_stop(wg_stream_t *s);
/* Clock out one byte MSB-first; ack=0 -> ACK (SDA low on 9th clock)        */
void wg_byte(wg_stream_t *s, uint8_t byte, uint8_t nak);

/* Convenience: full transactions -------------------------------------------
 * addr7 + dir are combined into the address byte. addr_nak: address NAKed
 * (no data phase follows). final_nak: last data byte NAKed (normal for the
 * master terminating a read).                                              */
void wg_txn(wg_stream_t *s, uint8_t addr7, uint8_t dir_read,
            const uint8_t *data, size_t len,
            uint8_t addr_nak, uint8_t final_nak, uint8_t send_stop);

#endif /* WAVEFORM_GEN_H */
