/**
 * [v0.1]
 ******************************************************************************
 * @file    edge_ring.h
 * @brief   Bus-edge ring between the EXTI edge ISR (producer) and the main
 *          loop decoder (consumer) - fw 1.6, review B30/B31.
 *
 *          The ISR stores, per line change, the 16-bit TIM3 microsecond
 *          count and the line state (bit 0 = SCL, bit 1 = SDA). The main
 *          loop pops entries and extends the 16-bit time to the decoder's
 *          32-bit microseconds against a running base:
 *
 *            t32 = base + (uint16_t)(t16 - (uint16_t)base);  base = t32
 *
 *          This is exact while consecutive entries are < 65.536 ms apart.
 *          Longer gaps only happen on an idle bus, where the ring is empty,
 *          so the main loop re-anchors the base with edge_ring_idle_sync()
 *          every pass. It must read the clock BEFORE testing for empty, so
 *          any edge pushed later carries a time >= the new base.
 *
 *          Single producer / single consumer: head is written only by the
 *          ISR, tail only by the main loop, so no locking is needed on a
 *          single-core M0+ (aligned 16-bit stores are atomic).
 *
 *          Pure C, no hardware access: unit-tested on the host
 *          (embedded/tests/host/test_edge_ring.c).
 ******************************************************************************
 */
#ifndef EDGE_RING_H
#define EDGE_RING_H

#include <stdint.h>

#ifndef EDGE_RING_SIZE
#define EDGE_RING_SIZE          1024U   /* entries, power of two            */
#endif
#if (EDGE_RING_SIZE & (EDGE_RING_SIZE - 1U)) != 0U
#error "EDGE_RING_SIZE must be a power of two"
#endif
#define EDGE_RING_MASK          (EDGE_RING_SIZE - 1U)

#define EDGE_SCL                0x01U
#define EDGE_SDA                0x02U

typedef struct
{
    volatile uint16_t head;             /* next write (ISR only)            */
    volatile uint16_t tail;             /* next read (main loop only)       */
    volatile uint32_t overflow;         /* edges dropped: ring full (ISR)   */
    uint32_t base_us;                   /* 32-bit time of the last pop or   */
                                        /* idle sync (main loop only)       */
    uint16_t t16[EDGE_RING_SIZE];       /* TIM3 microsecond count           */
    uint8_t  lines[EDGE_RING_SIZE];     /* EDGE_SCL | EDGE_SDA              */
} edge_ring_t;

/** Empty the ring and anchor the time base (call with the producer off). */
static inline void edge_ring_reset(edge_ring_t *r, uint32_t now_us)
{
    r->head     = 0U;
    r->tail     = 0U;
    r->overflow = 0U;
    r->base_us  = now_us;
}

/** Producer (ISR). Returns 0 and counts an overflow when the ring is full. */
static inline uint8_t edge_ring_push(edge_ring_t *r, uint16_t t16, uint8_t lines)
{
    const uint16_t h    = r->head;
    const uint16_t next = (uint16_t)((h + 1U) & EDGE_RING_MASK);
    if (next == r->tail)
    {
        r->overflow++;
        return 0U;
    }
    r->t16[h]   = t16;
    r->lines[h] = lines;
    r->head     = next;                 /* publish after the data           */
    return 1U;
}

static inline uint8_t edge_ring_empty(const edge_ring_t *r)
{
    return (uint8_t)(r->head == r->tail);
}

static inline uint16_t edge_ring_used(const edge_ring_t *r)
{
    return (uint16_t)((r->head - r->tail) & EDGE_RING_MASK);
}

/** Consumer: re-anchor the time base while the bus is quiet. now_us must
 *  have been read BEFORE this call tests for empty (see file comment).    */
static inline void edge_ring_idle_sync(edge_ring_t *r, uint32_t now_us)
{
    if (r->head == r->tail)
    {
        r->base_us = now_us;
    }
}

/** Consumer: pop the oldest edge with its 32-bit time. Returns 0 if empty. */
static inline uint8_t edge_ring_pop(edge_ring_t *r, uint32_t *t_us, uint8_t *lines)
{
    const uint16_t t = r->tail;
    if (t == r->head)
    {
        return 0U;
    }
    r->base_us += (uint16_t)(r->t16[t] - (uint16_t)r->base_us);
    *t_us  = r->base_us;
    *lines = r->lines[t];
    r->tail = (uint16_t)((t + 1U) & EDGE_RING_MASK);
    return 1U;
}

#endif /* EDGE_RING_H */
