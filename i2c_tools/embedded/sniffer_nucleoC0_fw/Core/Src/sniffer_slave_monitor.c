/**
 * [v0.1]
 ******************************************************************************
 * @file    sniffer_slave_monitor.c
 * @brief   I2C1-peripheral capture backend (see header for the model and
 *          the inherent limitations of this mode).
 *
 * Peripheral setup notes (STM32C0 reference manual RM0490, I2C chapter):
 *   - OA2 = 0x00 with OA2MSK = 7 -> the peripheral compares no address bits,
 *     i.e. it matches every 7-bit address on the bus.
 *   - NOSTRETCH = 1 -> the slave never holds SCL low; combined with TXDR
 *     preloaded to 0xFF (open-drain "release"), read transfers pass through
 *     without electrical interference while the real slave drives SDA.
 *   - All event handling is flag-polled; no interrupts anywhere in this
 *     firmware.
 ******************************************************************************
 */
#include "stm32c0xx.h"
#include "stm32c0xx_ll_bus.h"
#include "stm32c0xx_ll_gpio.h"
#include "stm32c0xx_ll_i2c.h"

#include "sniffer_config.h"
#include "sniffer_slave_monitor.h"

static i2c_txn_t s_cur;          /* record being assembled                  */
static uint8_t   s_active;       /* inside an address phase                 */
static uint8_t   s_restart;      /* next ADDR is a repeated START           */

static inline void cur_reset(void)
{
    s_cur.t_us     = 0U;
    s_cur.addr7    = 0U;
    s_cur.dir_read = 0U;
    s_cur.nak      = 0U;
    s_cur.restart  = 0U;
    s_cur.stop     = 0U;
    s_cur.overflow = 0U;
    s_cur.timeout  = 0U;
    s_cur.framing  = 0U;
    s_cur.len      = 0U;
    s_cur.scl_sum_us = 0U;          /* peripheral owns PA9: not measurable   */
    s_cur.scl_cnt    = 0U;
}

void smon_init(void)
{
    SNIFF_GPIO_CLK_EN();
    LL_APB1_GRP1_EnableClock(LL_APB1_GRP1_PERIPH_I2C1);

    /* PA9/PA10 -> I2C1 SCL/SDA, AF6, open-drain, no pulls (bus has them)   */
    LL_GPIO_SetPinMode(SNIFF_GPIO_PORT, LL_GPIO_PIN_9,  LL_GPIO_MODE_ALTERNATE);
    LL_GPIO_SetPinMode(SNIFF_GPIO_PORT, LL_GPIO_PIN_10, LL_GPIO_MODE_ALTERNATE);
    LL_GPIO_SetPinOutputType(SNIFF_GPIO_PORT, LL_GPIO_PIN_9,  LL_GPIO_OUTPUT_OPENDRAIN);
    LL_GPIO_SetPinOutputType(SNIFF_GPIO_PORT, LL_GPIO_PIN_10, LL_GPIO_OUTPUT_OPENDRAIN);
    LL_GPIO_SetPinPull(SNIFF_GPIO_PORT, LL_GPIO_PIN_9,  LL_GPIO_PULL_NO);
    LL_GPIO_SetPinPull(SNIFF_GPIO_PORT, LL_GPIO_PIN_10, LL_GPIO_PULL_NO);
    LL_GPIO_SetAFPin_8_15(SNIFF_GPIO_PORT, LL_GPIO_PIN_9,  LL_GPIO_AF_6);
    LL_GPIO_SetAFPin_8_15(SNIFF_GPIO_PORT, LL_GPIO_PIN_10, LL_GPIO_AF_6);

    LL_I2C_Disable(I2C1);

    /* Slave-only: TIMINGR matters little (SCL is externally driven); a     */
    /* sane analog-filter-on configuration is kept for signal conditioning. */
    LL_I2C_SetTiming(I2C1, 0x00000000U);
    LL_I2C_EnableAnalogFilter(I2C1);
    LL_I2C_SetDigitalFilter(I2C1, 0U);

    /* Never stretch the clock - mandatory for transparency                 */
    LL_I2C_DisableClockStretching(I2C1);

    /* Match-all secondary own address                                      */
    LL_I2C_SetOwnAddress2(I2C1, 0x00U, LL_I2C_OWNADDRESS2_MASK07);
    LL_I2C_DisableOwnAddress1(I2C1);

    LL_I2C_Enable(I2C1);

    cur_reset();
    s_active  = 0U;
    s_restart = 0U;
}

void smon_enable(uint8_t on)
{
    if (on != 0U)
    {
        LL_I2C_EnableOwnAddress2(I2C1);
    }
    else
    {
        LL_I2C_DisableOwnAddress2(I2C1);
    }
    cur_reset();
    s_active  = 0U;
    s_restart = 0U;
}

uint32_t smon_bus_hz(void)
{
    return 0U;
}

uint8_t smon_poll(i2c_txn_t *out, uint32_t t_us)
{
    uint8_t emitted = 0U;

    /* ---- Address matched ------------------------------------------------ */
    if (LL_I2C_IsActiveFlag_ADDR(I2C1) != 0U)
    {
        if (s_active != 0U)
        {
            /* repeated START: close the running record without STOP        */
            s_cur.stop = 0U;
            *out       = s_cur;
            emitted    = 1U;
            s_restart  = 1U;
        }

        cur_reset();
        s_cur.t_us     = t_us;
        s_cur.restart  = s_restart;
        s_cur.addr7    = (uint8_t)(LL_I2C_GetAddressMatchCode(I2C1) >> 1);
        s_cur.dir_read = (LL_I2C_GetTransferDirection(I2C1) ==
                          LL_I2C_DIRECTION_READ) ? 1U : 0U;
        s_active  = 1U;
        s_restart = 0U;

        if (s_cur.dir_read != 0U)
        {
            /* Read transfer: stay electrically transparent. 0xFF = SDA     */
            /* released on every bit; the real slave drives the data.       */
            LL_I2C_ClearFlag_TXE(I2C1);        /* flush, then preload       */
            LL_I2C_TransmitData8(I2C1, 0xFFU);
        }
        LL_I2C_ClearFlag_ADDR(I2C1);
    }

    /* ---- Write payload byte --------------------------------------------- */
    if (LL_I2C_IsActiveFlag_RXNE(I2C1) != 0U)
    {
        const uint8_t b = LL_I2C_ReceiveData8(I2C1);
        if (s_active != 0U)
        {
            if (s_cur.len < TXN_MAX_DATA)
            {
                s_cur.data[s_cur.len] = b;
                s_cur.len++;
            }
            else
            {
                s_cur.overflow = 1U;
            }
        }
    }

    /* ---- Keep TXDR fed with 0xFF during read transfers ------------------ */
    if ((s_active != 0U) && (s_cur.dir_read != 0U) &&
        (LL_I2C_IsActiveFlag_TXIS(I2C1) != 0U))
    {
        LL_I2C_TransmitData8(I2C1, 0xFFU);
    }

    /* ---- NACK observed --------------------------------------------------- */
    if (LL_I2C_IsActiveFlag_NACK(I2C1) != 0U)
    {
        LL_I2C_ClearFlag_NACK(I2C1);
        if (s_active != 0U)
        {
            s_cur.nak = 1U;
        }
    }

    /* ---- STOP ------------------------------------------------------------ */
    if (LL_I2C_IsActiveFlag_STOP(I2C1) != 0U)
    {
        LL_I2C_ClearFlag_STOP(I2C1);
        if (s_active != 0U)
        {
            s_cur.stop = 1U;
            *out       = s_cur;
            emitted    = 1U;
        }
        s_active  = 0U;
        s_restart = 0U;

        /* drain any leftover receive data                                  */
        if (LL_I2C_IsActiveFlag_RXNE(I2C1) != 0U)
        {
            (void)LL_I2C_ReceiveData8(I2C1);
        }
    }

    return emitted;
}
