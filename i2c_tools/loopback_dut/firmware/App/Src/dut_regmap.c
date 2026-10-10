/**
 * [v0.1]
 * @file    dut_regmap.c
 * @brief   Synthetic responder register map (see dut_regmap.h, PROTOCOL.md §4).
 */
#include "dut_regmap.h"

void dut_regmap_init(dut_regmap_t *m, uint16_t base)
{
    m->base   = base;
    m->ptr    = 0U;
    m->subcmd = 0U;
    m->sub_lo = 0U;
}

void dut_regmap_write(dut_regmap_t *m, uint32_t index, uint8_t byte)
{
    if (index == 0U)
    {
        m->ptr = byte;
        return;
    }
    if (m->ptr == DUT_BLOCK_START)
    {
        if (index == 1U)
        {
            m->sub_lo = byte;
        }
        else if (index == 2U)
        {
            m->subcmd = (uint16_t)(m->sub_lo | ((uint16_t)byte << 8));
        }
    }
    /* other data bytes: acknowledged, not stored (reads stay a pure
     * function of the pointer, so expected values never depend on history
     * other than the subcommand)                                           */
}

static uint8_t block_byte(const dut_regmap_t *m, uint32_t off)
{
    const uint8_t lo = (uint8_t)(m->subcmd & 0xFFU);
    const uint8_t hi = (uint8_t)(m->subcmd >> 8);

    if (off == 0U) { return lo; }
    if (off == 1U) { return hi; }
    if (off < 2U + DUT_BLOCK_DATA_LEN)
    {
        return (uint8_t)((0x40U + (off - 2U)) ^ lo);
    }
    if (off == 2U + DUT_BLOCK_DATA_LEN)            /* 0x60 checksum        */
    {
        uint32_t sum = (uint32_t)lo + hi;
        for (uint32_t i = 0U; i < DUT_BLOCK_DATA_LEN; i++)
        {
            sum += (uint8_t)((0x40U + i) ^ lo);
        }
        return (uint8_t)(~sum & 0xFFU);
    }
    if (off == 3U + DUT_BLOCK_DATA_LEN)            /* 0x61 length          */
    {
        return (uint8_t)(DUT_BLOCK_DATA_LEN + 4U);
    }
    return 0xFFU;
}

uint8_t dut_regmap_read(const dut_regmap_t *m, uint32_t k)
{
    if ((m->ptr >= DUT_BLOCK_START) && (m->ptr <= DUT_BLOCK_END))
    {
        return block_byte(m, (uint32_t)(m->ptr - DUT_BLOCK_START) + k);
    }
    const uint16_t word = (uint16_t)(m->base + m->ptr + (k >> 1));
    return (uint8_t)((k & 1U) ? (word >> 8) : (word & 0xFFU));
}

uint8_t dut_crc8(const uint8_t *p, uint32_t n)
{
    uint8_t crc = 0U;
    for (uint32_t i = 0U; i < n; i++)
    {
        crc = dut_crc8_update(crc, p[i]);
    }
    return crc;
}
