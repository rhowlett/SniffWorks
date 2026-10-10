/**
 * [v0.1]
 * test_i2c_decoder.c - host unit tests for the pure I2C bit-bang decoder.
 *
 * Build & run: make -C embedded/tests/host test
 *
 * Coverage:
 *   - single write transaction (address, data, ACKs, STOP)
 *   - single read with terminating master NAK
 *   - write + repeated-START + read (register-read pattern, BQ76905 style)
 *   - address NAK (device absent)
 *   - zero-length write (SMBus quick command)
 *   - data overflow beyond TXN_MAX_DATA
 *   - back-to-back transaction stream integrity
 *   - bus clock estimation
 *   - per-phase SCL measurement (fw 1.3): 100/400 kHz with 1 us timestamp
 *     quantisation, non-integer periods, clock stretch excluded, speed step
 *     followed by bus_hz, Sr phases measured independently
 *   - sparse sampling (decoder fed only line *changes*, like the firmware)
 *   - repeated-START stalls: fw 1.0 corruption repro, and the fw 1.1 bit-
 *     slip ("working test 1.csv") now flagged by the framing check
 *   - zero-copy record ring (queue order, full-ring drop)
 *   - missed-START detection
 */
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

#include "i2c_bitbang_decoder.h"
#include "waveform_gen.h"

static int g_failures = 0;
static int g_checks   = 0;

#define CHECK(cond, msg) do {                                        \
    g_checks++;                                                      \
    if (!(cond)) {                                                   \
        g_failures++;                                                \
        printf("  FAIL: %s  (%s:%d)\n", msg, __FILE__, __LINE__);    \
    }                                                                \
} while (0)

/* Run a stream through the decoder, collecting completed transactions.     */
#define MAX_OUT 64
static i2c_txn_t g_out[MAX_OUT];
static size_t    g_out_n;
static size_t    g_framing_n;        /* records flagged bit-slipped        */

/* Take the oldest queued record off the decoder ring. [XREF: zero-copy-ring] */
static int take(i2c_decoder_t *d, i2c_txn_t *dst)
{
    const i2c_txn_t *t = i2c_dec_peek(d);
    if (t == NULL)
    {
        return 0;
    }
    *dst = *t;
    i2c_dec_pop(d);
    return 1;
}

static void run_stream(i2c_decoder_t *d, const wg_stream_t *s, int only_changes)
{
    uint8_t prev_scl = 2U, prev_sda = 2U;   /* force first sample through   */
    g_out_n = 0;
    g_framing_n = 0;
    for (size_t i = 0; i < s->n; i++)
    {
        if (only_changes &&
            (s->scl[i] == prev_scl) && (s->sda[i] == prev_sda))
        {
            continue;   /* emulate the firmware's IDR-change gate           */
        }
        prev_scl = s->scl[i];
        prev_sda = s->sda[i];
        if (i2c_dec_sample(d, s->scl[i], s->sda[i], s->t_us[i]) == I2C_DEC_EVT_TXN)
        {
            i2c_txn_t t;
            if (take(d, &t))
            {
                g_framing_n += t.framing;
                if (g_out_n < MAX_OUT)
                {
                    g_out[g_out_n++] = t;
                }
            }
        }
    }
}

/* ------------------------------------------------------------------------ */
static void test_single_write(void)
{
    printf("test_single_write\n");
    static wg_stream_t s;
    i2c_decoder_t d;
    const uint8_t payload[] = { 0x3E, 0x01, 0x02 };

    wg_init(&s, 4, 1);
    wg_txn(&s, 0x08, 0, payload, sizeof payload, 0, 0, 1);

    i2c_dec_init(&d);
    run_stream(&d, &s, 0);

    CHECK(g_out_n == 1, "exactly one transaction");
    CHECK(g_out[0].addr7 == 0x08, "address 0x08");
    CHECK(g_out[0].dir_read == 0, "direction write");
    CHECK(g_out[0].len == 3, "3 data bytes");
    CHECK(memcmp(g_out[0].data, payload, 3) == 0, "payload matches");
    CHECK(g_out[0].nak == 0, "fully ACKed");
    CHECK(g_out[0].restart == 0, "not a restart");
    CHECK(g_out[0].stop == 1, "closed by STOP");
    CHECK(g_out[0].overflow == 0, "no overflow");
}

/* ------------------------------------------------------------------------ */
static void test_single_read_master_nak(void)
{
    printf("test_single_read_master_nak\n");
    static wg_stream_t s;
    i2c_decoder_t d;
    const uint8_t payload[] = { 0xAB, 0xCD };

    wg_init(&s, 4, 1);
    /* master NAKs the final byte of a read - normal protocol               */
    wg_txn(&s, 0x50, 1, payload, sizeof payload, 0, 1, 1);

    i2c_dec_init(&d);
    run_stream(&d, &s, 0);

    CHECK(g_out_n == 1, "one transaction");
    CHECK(g_out[0].addr7 == 0x50, "address 0x50");
    CHECK(g_out[0].dir_read == 1, "direction read");
    CHECK(g_out[0].len == 2, "2 data bytes");
    CHECK(memcmp(g_out[0].data, payload, 2) == 0, "payload matches");
    CHECK(g_out[0].nak == 1, "final NAK recorded");
    CHECK(g_out[0].stop == 1, "closed by STOP");
}

/* ------------------------------------------------------------------------ */
static void test_write_restart_read(void)
{
    printf("test_write_restart_read (register-read pattern)\n");
    static wg_stream_t s;
    i2c_decoder_t d;
    const uint8_t reg[]  = { 0x9A };               /* register pointer      */
    const uint8_t resp[] = { 0x05, 0x69, 0x77 };   /* device response       */

    wg_init(&s, 4, 1);
    wg_txn(&s, 0x08, 0, reg, 1, 0, 0, 0);          /* write, NO stop        */
    wg_txn(&s, 0x08, 1, resp, 3, 0, 1, 1);         /* repeated START + read */

    i2c_dec_init(&d);
    run_stream(&d, &s, 0);

    CHECK(g_out_n == 2, "two transaction records");

    CHECK(g_out[0].dir_read == 0, "first is write");
    CHECK(g_out[0].len == 1 && g_out[0].data[0] == 0x9A, "register byte");
    CHECK(g_out[0].stop == 0, "write closed by restart, not STOP");
    CHECK(g_out[0].restart == 0, "write opened by plain START");

    CHECK(g_out[1].dir_read == 1, "second is read");
    CHECK(g_out[1].restart == 1, "read flagged as restart");
    CHECK(g_out[1].stop == 1, "read closed by STOP");
    CHECK(g_out[1].len == 3, "read length 3");
    CHECK(memcmp(g_out[1].data, resp, 3) == 0, "read payload");
    CHECK(g_framing_n == 0, "clean restart: no framing flag");
}

/* ------------------------------------------------------------------------ */
static void test_address_nak(void)
{
    printf("test_address_nak (device absent)\n");
    static wg_stream_t s;
    i2c_decoder_t d;

    wg_init(&s, 4, 1);
    wg_txn(&s, 0x77, 0, NULL, 0, 1, 0, 1);   /* address NAKed */

    i2c_dec_init(&d);
    run_stream(&d, &s, 0);

    CHECK(g_out_n == 1, "one transaction");
    CHECK(g_out[0].addr7 == 0x77, "address 0x77");
    CHECK(g_out[0].nak == 1, "NAK flagged");
    CHECK(g_out[0].len == 0, "no data");
}

/* ------------------------------------------------------------------------ */
static void test_quick_command(void)
{
    printf("test_quick_command (zero-length write)\n");
    static wg_stream_t s;
    i2c_decoder_t d;

    wg_init(&s, 4, 1);
    wg_txn(&s, 0x2A, 0, NULL, 0, 0, 0, 1);

    i2c_dec_init(&d);
    run_stream(&d, &s, 0);

    CHECK(g_out_n == 1, "one transaction");
    CHECK(g_out[0].addr7 == 0x2A && g_out[0].len == 0 && g_out[0].nak == 0,
          "ACKed zero-length write");
}

/* ------------------------------------------------------------------------ */
static void test_overflow(void)
{
    printf("test_overflow (> TXN_MAX_DATA bytes)\n");
    static wg_stream_t s;
    i2c_decoder_t d;
    uint8_t big[TXN_MAX_DATA + 8];
    for (size_t i = 0; i < sizeof big; i++) { big[i] = (uint8_t)i; }

    wg_init(&s, 2, 1);
    wg_txn(&s, 0x10, 0, big, sizeof big, 0, 0, 1);

    i2c_dec_init(&d);
    run_stream(&d, &s, 0);

    CHECK(g_out_n == 1, "one transaction");
    CHECK(g_out[0].overflow == 1, "overflow flagged");
    CHECK(g_out[0].len == TXN_MAX_DATA, "length clamped");
    CHECK(g_out[0].data[TXN_MAX_DATA - 1] == (uint8_t)(TXN_MAX_DATA - 1),
          "kept bytes intact");
}

/* ------------------------------------------------------------------------ */
static void test_stream_integrity(void)
{
    printf("test_stream_integrity (back-to-back transactions)\n");
    static wg_stream_t s;
    i2c_decoder_t d;
    const uint8_t a[] = { 0x11 };
    const uint8_t b[] = { 0x22, 0x33 };

    wg_init(&s, 4, 1);
    for (int i = 0; i < 5; i++)
    {
        wg_txn(&s, 0x08, 0, a, 1, 0, 0, 1);
        wg_idle(&s, 3);
        wg_txn(&s, 0x09, 1, b, 2, 0, 1, 1);
        wg_idle(&s, 3);
    }

    i2c_dec_init(&d);
    run_stream(&d, &s, 0);

    CHECK(g_out_n == 10, "ten transactions");
    int ok = 1;
    for (size_t i = 0; i < g_out_n; i += 2)
    {
        ok &= (g_out[i].addr7 == 0x08) && (g_out[i].len == 1);
        ok &= (g_out[i + 1].addr7 == 0x09) && (g_out[i + 1].len == 2);
    }
    CHECK(ok, "alternating pattern intact");
    CHECK(g_framing_n == 0, "no framing flags on a clean stream");
    CHECK(d.txn_count == 10, "decoder counter matches");
}

/* ------------------------------------------------------------------------ */
static void test_bus_hz_estimate(void)
{
    printf("test_bus_hz_estimate\n");
    static wg_stream_t s;
    i2c_decoder_t d;
    const uint8_t payload[] = { 0x55 };

    /* 4 quarter-bits * 2.5 us = 10 us bit period -> 100 kHz               */
    wg_init(&s, 1, 2);   /* 1 sample per quarter, 2 us step -> 8 us period  */
    wg_txn(&s, 0x08, 0, payload, 1, 0, 0, 1);

    i2c_dec_init(&d);
    run_stream(&d, &s, 0);

    const uint32_t hz = i2c_dec_bus_hz(&d);
    CHECK(hz >= 100000 && hz <= 140000, "estimate near 125 kHz");
    CHECK(g_out_n == 1 && i2c_txn_scl_hz(&g_out[0]) == 125000U,
          "8 us periods -> record scl_hz exactly 125000");
    CHECK(hz == 125000U, "bus_hz == last record's scl_hz");
}

/* Within `ppm` parts-per-million of `want`.                                 */
static int near_hz(uint32_t got, uint32_t want, uint32_t ppm)
{
    const uint32_t diff = (got > want) ? (got - want) : (want - got);
    return ((uint64_t)diff * 1000000U) <= ((uint64_t)want * ppm);
}

/* 2-byte register write + 2-byte read at a given ns step / quarter size.   */
static void scl_pattern(wg_stream_t *s, uint32_t spq)
{
    const uint8_t w[] = { 0x3E, 0x12 };
    const uint8_t r[] = { 0x34, 0x12 };
    s->samples_per_quarter_bit = spq;
    wg_txn(s, 0x6B, 0, w, 2, 0, 0, 1);
    wg_idle(s, 8);
    wg_txn(s, 0x6B, 1, r, 2, 0, 1, 1);
    wg_idle(s, 8);
}

static void test_scl_hz_100k_400k(void)
{
    printf("test_scl_hz_100k_400k\n");
    static wg_stream_t s;
    i2c_decoder_t d;

    /* 100 kHz: 125 ns sampler, quarter = 20 samples = 2.5 us               */
    wg_init_ns(&s, 20, 125);
    scl_pattern(&s, 20);
    i2c_dec_init(&d);
    run_stream(&d, &s, 1);
    CHECK(g_out_n == 2, "100k: two phases");
    CHECK(near_hz(i2c_txn_scl_hz(&g_out[0]), 100000U, 5000U), "100k write within 0.5 %");
    CHECK(near_hz(i2c_txn_scl_hz(&g_out[1]), 100000U, 5000U), "100k read within 0.5 %");

    /* 400 kHz: quarter = 5 samples = 625 ns; 2.5 us periods read as 2/3 us */
    wg_init_ns(&s, 5, 125);
    scl_pattern(&s, 5);
    i2c_dec_init(&d);
    run_stream(&d, &s, 1);
    CHECK(g_out_n == 2, "400k: two phases");
    CHECK(near_hz(i2c_txn_scl_hz(&g_out[0]), 400000U, 20000U), "400k write within 2 %");
    CHECK(near_hz(i2c_txn_scl_hz(&g_out[1]), 400000U, 20000U), "400k read within 2 %");
    printf("  measured 400k phases: %u, %u Hz\n",
           (unsigned)i2c_txn_scl_hz(&g_out[0]), (unsigned)i2c_txn_scl_hz(&g_out[1]));

    /* non-integer period: 100 ns sampler, quarter 7 = 2.8 us -> 357143 Hz  */
    wg_init_ns(&s, 7, 100);
    scl_pattern(&s, 7);
    i2c_dec_init(&d);
    run_stream(&d, &s, 1);
    CHECK(near_hz(i2c_txn_scl_hz(&g_out[0]), 357143U, 20000U), "357 kHz within 2 %");
}

static void test_scl_hz_stretch_excluded(void)
{
    printf("test_scl_hz_stretch_excluded\n");
    static wg_stream_t s;
    i2c_decoder_t d;
    const uint8_t w[] = { 0x10, 0x20, 0x30 };

    /* 100 kHz, 125 ns sampler; slave stretches ~200 us mid-byte (LB-14)    */
    wg_init_ns(&s, 20, 125);
    wg_start(&s);
    wg_byte(&s, (uint8_t)(0x6B << 1), 0);
    wg_stretch_next_byte(&s, 3, 1600U);        /* 1600 x 125 ns = 200 us    */
    wg_byte(&s, w[0], 0);
    wg_idle(&s, 40);                           /* 100 us inter-byte stretch */
    wg_byte(&s, w[1], 0);
    wg_byte(&s, w[2], 0);
    wg_stop(&s);

    i2c_dec_init(&d);
    run_stream(&d, &s, 1);
    CHECK(g_out_n == 1 && g_out[0].len == 3, "stretched write decoded");
    CHECK(near_hz(i2c_txn_scl_hz(&g_out[0]), 100000U, 5000U),
          "stretch excluded: still 100 kHz within 0.5 %");
}

static void test_scl_hz_follows_speed_step(void)
{
    printf("test_scl_hz_follows_speed_step\n");
    static wg_stream_t s;
    i2c_decoder_t d;

    /* 400 kHz traffic, then the master drops to 100 kHz in the same run.   */
    wg_init_ns(&s, 5, 125);
    scl_pattern(&s, 5);                        /* records 0,1 @ 400k        */
    scl_pattern(&s, 20);                       /* records 2,3 @ 100k        */
    i2c_dec_init(&d);
    run_stream(&d, &s, 1);
    CHECK(g_out_n == 4, "four phases");
    CHECK(near_hz(i2c_txn_scl_hz(&g_out[1]), 400000U, 20000U), "phase 1 at 400k");
    CHECK(near_hz(i2c_txn_scl_hz(&g_out[2]), 100000U, 5000U), "phase 2 at 100k");
    CHECK(i2c_dec_bus_hz(&d) == i2c_txn_scl_hz(&g_out[3]),
          "bus_hz follows the step down (not a sticky minimum)");
    CHECK(near_hz(i2c_dec_bus_hz(&d), 100000U, 5000U), "bus_hz ~100k after step");
}

static void test_scl_hz_restart_phases(void)
{
    printf("test_scl_hz_restart_phases\n");
    static wg_stream_t s;
    i2c_decoder_t d;
    const uint8_t reg[] = { 0x02 };
    const uint8_t rsp[] = { 0xA0, 0x02 };

    /* pointer write, repeated START, read - both phases at 400 kHz         */
    wg_init_ns(&s, 5, 125);
    wg_txn(&s, 0x6B, 0, reg, 1, 0, 0, 0);
    wg_txn(&s, 0x6B, 1, rsp, 2, 0, 1, 1);
    i2c_dec_init(&d);
    run_stream(&d, &s, 1);
    CHECK(g_out_n == 2 && g_out[1].restart == 1, "write + Sr read");
    CHECK(near_hz(i2c_txn_scl_hz(&g_out[0]), 400000U, 20000U), "write phase measured");
    CHECK(near_hz(i2c_txn_scl_hz(&g_out[1]), 400000U, 20000U), "Sr read phase measured");
}

/* ------------------------------------------------------------------------ */
static void test_change_only_sampling(void)
{
    printf("test_change_only_sampling (firmware IDR-change gate)\n");
    static wg_stream_t s;
    i2c_decoder_t d;
    const uint8_t reg[]  = { 0x12 };
    const uint8_t resp[] = { 0x9A, 0xBC };

    wg_init(&s, 6, 1);
    wg_txn(&s, 0x41, 0, reg, 1, 0, 0, 0);
    wg_txn(&s, 0x41, 1, resp, 2, 0, 1, 1);

    i2c_dec_init(&d);
    run_stream(&d, &s, 1 /* only feed changes */);

    CHECK(g_out_n == 2, "two records via change-gated feed");
    CHECK(g_out[1].restart == 1 && g_out[1].len == 2, "restart read intact");
    CHECK(g_framing_n == 0, "change-gated feed: no framing flags");
}

/* ------------------------------------------------------------------------ */

/* ------------------------------------------------------------------------ */
/* Repeated-START corruption: reproduces the field capture where every      */
/* restart phase decoded with a garbage address (e.g. 0x5C instead of       */
/* 0x6B). Root cause: main.c encoded + enqueued the UART frame INSIDE the   */
/* sample loop when a phase completed; the sampling gap swallowed the Sr    */
/* setup and the first address bits of the immediately-following phase.     */
/* This test (a) proves the decoder core is sound under continuous          */
/* sampling, and (b) reproduces the corruption by skipping samples right    */
/* after the first TXN event, as the old main loop effectively did.         */
/* ------------------------------------------------------------------------ */
static void test_restart_with_emission_gap(void)
{
    printf("test_restart_with_emission_gap\n");

    /* BQ25731-style register read: W 0x6B [0x2E], Sr, R 0x6B [0x40] N P    */
    wg_stream_t wf;
    wg_init(&wf, 4, 1);                      /* 4 samples/quarter-bit       */
    wg_idle(&wf, 8);
    {
        const uint8_t ptr = 0x2E;
        wg_txn(&wf, 0x6B, 0U, &ptr, 1, 0U, 0U, 0U);   /* write, no stop    */
    }
    wg_start(&wf);                            /* repeated START             */
    wg_byte(&wf, (uint8_t)((0x6B << 1) | 1U), 0U);
    wg_byte(&wf, 0x40, 1U);                   /* data, master NAK           */
    wg_stop(&wf);
    wg_idle(&wf, 8);

    /* (a) continuous sampling: both phases decode cleanly                  */
    {
        i2c_decoder_t dec;
        i2c_dec_init(&dec);
        i2c_txn_t got[4];
        int n = 0;
        for (size_t i = 0; i < wf.n; i++)
        {
            if (i2c_dec_sample(&dec, wf.scl[i], wf.sda[i], wf.t_us[i])
                    == I2C_DEC_EVT_TXN && n < 4)
            {
                n += take(&dec, &got[n]);
            }
        }
        CHECK(n == 2, "continuous: two phases");
        CHECK(got[0].addr7 == 0x6B && got[0].dir_read == 0U &&
              got[0].len == 1 && got[0].data[0] == 0x2E,
              "continuous: pointer write clean");
        CHECK(got[1].addr7 == 0x6B && got[1].dir_read == 1U &&
              got[1].restart == 1U && got[1].len == 1 &&
              got[1].data[0] == 0x40,
              "continuous: restart read clean (addr 0x6B, R, 0x40)");
    }

    /* (b) a sampling gap right after the first phase corrupts the restart  */
    {
        int corrupted_at_any_gap = 0;
        for (size_t gap = 6; gap <= 40; gap += 2)
        {
            i2c_decoder_t dec;
            i2c_dec_init(&dec);
            i2c_txn_t got[4];
            int n = 0;
            size_t skip_until = 0;
            for (size_t i = 0; i < wf.n; i++)
            {
                if (i < skip_until)
                {
                    continue;                 /* "busy emitting the frame"  */
                }
                if (i2c_dec_sample(&dec, wf.scl[i], wf.sda[i], wf.t_us[i])
                        == I2C_DEC_EVT_TXN)
                {
                    i2c_txn_t t;
                    if (take(&dec, &t) && n < 4) { got[n] = t; }
                    n++;
                    if (n == 1)
                    {
                        skip_until = i + gap; /* old main loop's stall      */
                    }
                }
            }
            const int second_ok = (n == 2 && got[1].addr7 == 0x6B &&
                                   got[1].dir_read == 1U &&
                                   got[1].len == 1 &&
                                   got[1].data[0] == 0x40);
            if (!second_ok)
            {
                corrupted_at_any_gap = 1;
            }
        }
        CHECK(corrupted_at_any_gap,
              "a post-phase sampling stall corrupts the restart phase "
              "(field-capture bug reproduced)");
    }
}

/* ------------------------------------------------------------------------ */
/* fw 1.1 field bug ("working test 1.csv", Neware -> pack at 0x10, ~47 kHz): */
/* ChargingCurrent read  W 0x10 [14]  Sr  R 0x10 [00 01] N P  was logged as  */
/* Sr W 0x21 [00 03] with no NAK: main.c's ~20 us record copy at the Sr     */
/* swallowed SCL low->high of address bit 7 (SDA already low, so the IDR    */
/* change gate saw nothing). fw 1.2 removes the copy [XREF: zero-copy-ring]; */
/* this test pins (a) the exact slip signature and (b) that the framing     */
/* check flags it, so a future regression cannot pass silently.             */
/* ------------------------------------------------------------------------ */
static void build_sbs_read(wg_stream_t *wf, uint8_t hi)
{
    const uint8_t cmd = 0x14;               /* SBS ChargingCurrent           */
    wg_init(wf, 4, 1);                      /* 16 samples per bit            */
    wg_idle(wf, 8);
    wg_txn(wf, 0x10, 0U, &cmd, 1, 0U, 0U, 0U);
    wg_start(wf);
    wg_byte(wf, (uint8_t)((0x10 << 1) | 1U), 0U);
    wg_byte(wf, 0x00, 0U);
    wg_byte(wf, hi, 1U);                    /* master NAK ends the read      */
    wg_stop(wf);
    wg_idle(wf, 8);
}

/* Feed change-gated, skipping `gap` samples after the first TXN event.     */
static int run_with_gap(const wg_stream_t *wf, size_t gap, i2c_txn_t got[4])
{
    i2c_decoder_t dec;
    i2c_dec_init(&dec);
    int n = 0;
    size_t skip_until = 0;
    uint8_t ps = 2U, pd = 2U;
    for (size_t i = 0; i < wf->n; i++)
    {
        if (i < skip_until) { continue; }
        if (wf->scl[i] == ps && wf->sda[i] == pd) { continue; }
        ps = wf->scl[i];
        pd = wf->sda[i];
        if (i2c_dec_sample(&dec, wf->scl[i], wf->sda[i], wf->t_us[i])
                == I2C_DEC_EVT_TXN)
        {
            i2c_txn_t t;
            if (take(&dec, &t) && n < 4) { got[n] = t; }
            n++;
            if (n == 1) { skip_until = i + gap; }
        }
    }
    return n;
}

static void test_sr_bitslip_flagged(void)
{
    printf("test_sr_bitslip_flagged (working test 1.csv)\n");
    static wg_stream_t wf;
    i2c_txn_t got[4];

    for (int hi = 1; hi <= 2; hi++)
    {
        build_sbs_read(&wf, (uint8_t)hi);

        /* no stall (fw 1.2 hot path): clean, unflagged                     */
        int n = run_with_gap(&wf, 0, got);
        CHECK(n == 2 && got[0].addr7 == 0x10 && got[0].dir_read == 0U &&
              got[0].len == 1 && got[0].data[0] == 0x14 &&
              got[0].framing == 0U,
              "no stall: pointer write clean");
        CHECK(n == 2 && got[1].addr7 == 0x10 && got[1].dir_read == 1U &&
              got[1].len == 2 && got[1].data[0] == 0x00 &&
              got[1].data[1] == (uint8_t)hi && got[1].nak == 1U &&
              got[1].framing == 0U,
              "no stall: Sr read 0x10 R [00 0x] NAK, unflagged");

        /* 0.75-1.6 bit stall (fw 1.1 record copy): the field signature,    */
        /* now flagged                                                      */
        int all_sig = 1, all_flag = 1;
        for (size_t gap = 12; gap <= 26; gap += 2)
        {
            n = run_with_gap(&wf, gap, got);
            all_sig &= (n == 2 && got[1].addr7 == 0x21 &&
                        got[1].dir_read == 0U && got[1].len == 2 &&
                        got[1].data[0] == 0x00 &&
                        got[1].data[1] == (uint8_t)((hi << 1) | 1) &&
                        got[1].nak == 0U);
            all_flag &= (n == 2 && got[0].framing == 0U &&
                         got[1].framing == 1U);
        }
        CHECK(all_sig, "stall reproduces Sr W 0x21 [00 03|05], no NAK");
        CHECK(all_flag, "bit-slipped phase carries the framing flag");
    }

    /* any stall that corrupts the read must be flagged (no silent slips)   */
    {
        int silent = 0;
        build_sbs_read(&wf, 1U);
        for (size_t gap = 0; gap <= 60; gap++)
        {
            int n = run_with_gap(&wf, gap, got);
            const int clean = (n == 2 && got[1].addr7 == 0x10 &&
                               got[1].dir_read == 1U && got[1].len == 2 &&
                               got[1].data[1] == 0x01);
            if (n >= 2 && !clean && got[1].framing == 0U)
            {
                silent = 1;
            }
        }
        CHECK(!silent, "every corrupted restart phase is framing-flagged");
    }
}

/* ------------------------------------------------------------------------ */
static void test_zero_copy_ring(void)
{
    printf("test_zero_copy_ring\n");
    static wg_stream_t s;
    i2c_decoder_t d;

    wg_init(&s, 4, 1);
    for (uint8_t i = 0; i < I2C_DEC_RING_DEPTH + 2U; i++)
    {
        wg_txn(&s, (uint8_t)(0x20 + i), 0, &i, 1, 0, 0, 1);
        wg_idle(&s, 2);
    }

    /* never pop: ring holds DEPTH-1 records, the rest are dropped          */
    i2c_dec_init(&d);
    int n_txn = 0, n_drop = 0;
    for (size_t i = 0; i < s.n; i++)
    {
        const i2c_dec_event_t e = i2c_dec_sample(&d, s.scl[i], s.sda[i], s.t_us[i]);
        n_txn  += (e == I2C_DEC_EVT_TXN);
        n_drop += (e == I2C_DEC_EVT_DROPPED);
    }
    CHECK(n_txn == (int)(I2C_DEC_RING_DEPTH - 1U), "ring accepts DEPTH-1");
    CHECK(n_drop == 3, "overflow records reported as DROPPED");
    CHECK(d.drop_count == 3U, "drop counter");
    CHECK(i2c_dec_pending(&d) == I2C_DEC_RING_DEPTH - 1U, "pending count");

    int order_ok = 1;
    for (uint8_t i = 0; i < I2C_DEC_RING_DEPTH - 1U; i++)
    {
        i2c_txn_t t;
        order_ok &= take(&d, &t) && (t.addr7 == 0x20 + i) &&
                    (t.data[0] == i);
    }
    CHECK(order_ok, "FIFO order preserved, oldest first");
    CHECK(i2c_dec_peek(&d) == NULL && i2c_dec_pending(&d) == 0U,
          "empty after draining");
    i2c_dec_pop(&d);                        /* pop on empty is a no-op       */
    CHECK(i2c_dec_pending(&d) == 0U, "pop on empty is harmless");
}

/* ------------------------------------------------------------------------ */
static void test_missed_start(void)
{
    printf("test_missed_start\n");
    static wg_stream_t s;
    i2c_decoder_t d;
    const uint8_t data[] = { 0xA5, 0x5A };

    wg_init(&s, 4, 1);
    wg_idle(&s, 4);
    const size_t start_at = s.n;
    wg_txn(&s, 0x33, 0, data, 2, 0, 0, 1);
    wg_idle(&s, 4);
    wg_txn(&s, 0x34, 0, data, 2, 0, 0, 1);  /* next one must decode clean   */
    wg_idle(&s, 4);

    /* drop the START samples of the first transaction (flush stall)        */
    i2c_dec_init(&d);
    int n_err = 0;
    i2c_txn_t got[4];
    int n = 0;
    for (size_t i = 0; i < s.n; i++)
    {
        if (i >= start_at + 4 && i < start_at + 14) { continue; }
        const i2c_dec_event_t e = i2c_dec_sample(&d, s.scl[i], s.sda[i], s.t_us[i]);
        n_err += (e == I2C_DEC_EVT_BUS_ERROR);
        if (e == I2C_DEC_EVT_TXN && n < 4) { n += take(&d, &got[n]); }
    }
    CHECK(n_err == 1, "missed START reported exactly once");
    CHECK(n == 1 && got[0].addr7 == 0x34 && got[0].len == 2 &&
          got[0].framing == 0U, "decoder resyncs on the next START");
}

int main(void)
{
    test_restart_with_emission_gap();
    printf("=== i2c_bitbang_decoder host tests ===\n");
    test_single_write();
    test_single_read_master_nak();
    test_write_restart_read();
    test_address_nak();
    test_quick_command();
    test_overflow();
    test_stream_integrity();
    test_bus_hz_estimate();
    test_scl_hz_100k_400k();
    test_scl_hz_stretch_excluded();
    test_scl_hz_follows_speed_step();
    test_scl_hz_restart_phases();
    test_change_only_sampling();
    test_sr_bitslip_flagged();
    test_zero_copy_ring();
    test_missed_start();

    printf("=== %d checks, %d failures ===\n", g_checks, g_failures);
    return (g_failures == 0) ? EXIT_SUCCESS : EXIT_FAILURE;
}
