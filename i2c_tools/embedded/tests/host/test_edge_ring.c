/**
 * [v0.1]
 * test_edge_ring.c - host unit tests for edge_ring.h (fw 1.6, B30/B31).
 *
 * Coverage:
 *   - FIFO order, wrap of the indices, full ring -> overflow counted
 *   - 16 -> 32-bit time extension across TIM3 wraps (edges < 65.5 ms apart)
 *   - idle sync across a > 65.5 ms quiet bus, and the read-clock-first rule
 *   - end to end: a waveform pushed through the ring into the decoder
 *     decodes exactly as when fed directly
 */
#include <stdio.h>
#include <string.h>

#include "edge_ring.h"
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

static edge_ring_t r;

static void test_fifo_and_overflow(void)
{
    printf("test_fifo_and_overflow\n");
    uint32_t t; uint8_t l; uint32_t i; int ok = 1;
    edge_ring_reset(&r, 0U);
    CHECK(edge_ring_empty(&r), "empty after reset");
    CHECK(edge_ring_pop(&r, &t, &l) == 0U, "pop on empty returns 0");
    /* push/pop 3 * size so head and tail wrap several times */
    for (i = 0U; i < 3U * EDGE_RING_SIZE; i++)
    {
        ok &= edge_ring_push(&r, (uint16_t)(i * 3U), (uint8_t)(i & 3U));
        ok &= edge_ring_pop(&r, &t, &l);
        ok &= (t == i * 3U) && (l == (i & 3U));
    }
    CHECK(ok, "FIFO order and time across index wraps");
    /* fill: capacity is SIZE - 1 */
    for (i = 0U; i < EDGE_RING_SIZE - 1U; i++)
    {
        ok &= edge_ring_push(&r, 0U, 0U);
    }
    CHECK(ok, "SIZE-1 entries fit");
    CHECK(edge_ring_used(&r) == EDGE_RING_SIZE - 1U, "used == SIZE-1");
    CHECK(edge_ring_push(&r, 0U, 0U) == 0U, "push on full returns 0");
    CHECK(edge_ring_push(&r, 0U, 0U) == 0U && r.overflow == 2U, "overflow counted");
    edge_ring_pop(&r, &t, &l);
    CHECK(edge_ring_push(&r, 0U, 0U) == 1U, "space again after a pop");
}

static void test_time_extension(void)
{
    printf("test_time_extension\n");
    uint32_t t; uint8_t l;
    /* base near a TIM3 wrap and a 32-bit high part != 0 */
    const uint32_t base = 0x0003FFF0U;
    edge_ring_reset(&r, base);
    edge_ring_push(&r, (uint16_t)(base + 5U), 1U);       /* 0xFFF5            */
    edge_ring_push(&r, (uint16_t)(base + 20U), 0U);      /* wraps to 0x0004   */
    edge_ring_push(&r, (uint16_t)(base + 20U + 65000U), 1U);
    edge_ring_pop(&r, &t, &l);
    CHECK(t == base + 5U, "first edge before the TIM3 wrap");
    edge_ring_pop(&r, &t, &l);
    CHECK(t == base + 20U, "edge after the TIM3 wrap carries into bit 16");
    edge_ring_pop(&r, &t, &l);
    CHECK(t == base + 20U + 65000U, "65 ms between edges still exact");
}

static void test_idle_sync(void)
{
    printf("test_idle_sync\n");
    uint32_t t; uint8_t l;
    edge_ring_reset(&r, 1000U);
    edge_ring_push(&r, 1100U, 1U);
    edge_ring_pop(&r, &t, &l);
    CHECK(t == 1100U, "edge at 1100");
    /* 300 ms of idle bus: the main loop syncs every pass (read clock first) */
    edge_ring_idle_sync(&r, 1100U + 150000U);
    edge_ring_idle_sync(&r, 1100U + 300000U);
    edge_ring_push(&r, (uint16_t)(1100U + 300007U), 0U);
    edge_ring_pop(&r, &t, &l);
    CHECK(t == 1100U + 300007U, "edge after 300 ms idle gets the right time");
    /* sync with entries pending must not move the base */
    edge_ring_push(&r, (uint16_t)(1100U + 300010U), 1U);
    edge_ring_idle_sync(&r, 1100U + 999999U);
    edge_ring_pop(&r, &t, &l);
    CHECK(t == 1100U + 300010U, "sync ignored while the ring holds edges");
    /* clock read, then an edge arrives, then sync: base may only move to
     * the earlier clock value, so the edge stays correct                 */
    const uint32_t now = 1100U + 400000U;
    edge_ring_idle_sync(&r, now - 1U);              /* previous pass, empty */
    edge_ring_push(&r, (uint16_t)(now + 2U), 0U);   /* ISR after the read  */
    edge_ring_idle_sync(&r, now);                   /* not empty: no-op    */
    edge_ring_pop(&r, &t, &l);
    CHECK(t == now + 2U, "read-clock-first ordering");
}

/* waveform -> ring (only changes, 16-bit time) -> decoder, vs direct feed.
 * The stream's times are offset so the run crosses a TIM3 (16-bit) wrap. */
static wg_stream_t wg;
static void test_end_to_end(void)
{
    printf("test_end_to_end\n");
    static i2c_decoder_t da, db;
    const uint32_t off = 0x0000FF00U;
    const uint8_t w[1] = { 0x06U };
    const uint8_t rd[2] = { 0x06U, 0xA0U };
    i2c_dec_init(&da);
    i2c_dec_init(&db);
    wg_init_ns(&wg, 10U, 250U);                     /* 100 kHz, 4 MS/s      */
    wg_idle(&wg, 8U);
    wg_txn(&wg, 0x6BU, 0U, w, 1U, 0U, 0U, 0U);      /* W [06], no STOP      */
    wg_txn(&wg, 0x6BU, 1U, rd, 2U, 0U, 1U, 1U);     /* Sr R [06 A0] NAK, P  */
    wg_idle(&wg, 8U);

    edge_ring_reset(&r, off);
    uint8_t last = 0xFFU; size_t i; int ok = 1;
    uint32_t na = 0U, nb = 0U;
    for (i = 0U; i < wg.n; i++)
    {
        const uint32_t ts = wg.t_us[i] + off;
        if (i2c_dec_sample(&da, wg.scl[i], wg.sda[i], ts) == I2C_DEC_EVT_TXN) { na++; }
        const uint8_t lines = (uint8_t)(wg.scl[i] | (wg.sda[i] << 1));
        if (lines != last)
        {
            last = lines;
            ok &= edge_ring_push(&r, (uint16_t)ts, lines);
        }
        uint32_t t; uint8_t l;
        while (edge_ring_pop(&r, &t, &l))
        {
            ok &= (t == ts);
            if (i2c_dec_sample(&db, l & 1U, (uint8_t)(l >> 1), t) == I2C_DEC_EVT_TXN) { nb++; }
        }
    }
    CHECK(ok, "every ring edge carries the exact 32-bit time");
    CHECK(na == 2U && nb == 2U, "both paths close two phases");
    CHECK(da.count == 2U && db.count == 2U, "two records queued on both");
    const i2c_txn_t *a = &da.ring[1], *b = &db.ring[1];
    CHECK(b->addr7 == 0x6BU && b->dir_read == 1U && b->len == 2U &&
          b->data[0] == 0x06U && b->data[1] == 0xA0U && b->framing == 0U &&
          b->restart == 1U, "ring path decodes Sr R 0x6B [06 A0], no framing error");
    CHECK(db.ring[0].len == 1U && db.ring[0].data[0] == 0x06U, "ring path decodes W [06]");
    CHECK(memcmp(a->data, b->data, 2) == 0 && a->t_us == b->t_us &&
          a->scl_sum_us == b->scl_sum_us && a->scl_cnt == b->scl_cnt,
          "ring path == direct path (data, time, SCL measurement)");
    CHECK(i2c_txn_scl_hz(b) >= 98000U && i2c_txn_scl_hz(b) <= 102000U,
          "SCL measured ~100 kHz through the ring");
}

int main(void)
{
    test_fifo_and_overflow();
    test_time_extension();
    test_idle_sync();
    test_end_to_end();
    printf("=== %d checks, %d failures ===\n", g_checks, g_failures);
    return g_failures ? 1 : 0;
}
