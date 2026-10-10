/**
 ******************************************************************************
 * @file    sniffer_slave_monitor.h
 * @brief   I2C1-peripheral-based capture backend (SNIFF_MODE_SLAVE_MON).
 *
 *          The I2C1 peripheral is configured as a slave whose secondary own
 *          address (OA2) uses the match-all mask, so every address phase on
 *          the bus raises an ADDR event. Write payloads are captured from
 *          RXDR. For read transfers the peripheral preloads 0xFF into TXDR
 *          (never pulling SDA low - electrically transparent) and only the
 *          address + direction are recorded.
 *
 *          Known, inherent limitations - see sniffer_config.h.
 ******************************************************************************
 */
#ifndef SNIFFER_SLAVE_MONITOR_H
#define SNIFFER_SLAVE_MONITOR_H

#include <stdint.h>
#include "i2c_bitbang_decoder.h"   /* reuses i2c_txn_t as the common record */

#ifdef __cplusplus
extern "C" {
#endif

/** Configure PA9/PA10 as I2C1 (AF6, open-drain) and arm the match-all slave. */
void smon_init(void);

/** Enable/disable address matching (start/stop capture). */
void smon_enable(uint8_t on);

/**
 * Poll the I2C peripheral flags. When a transaction record completes it is
 * written to *out.
 * @param t_us current timestamp (microseconds)
 * @return 1 if *out was filled, else 0.
 */
uint8_t smon_poll(i2c_txn_t *out, uint32_t t_us);

/** Bus clock estimate - not measurable in this mode, always returns 0. */
uint32_t smon_bus_hz(void);

#ifdef __cplusplus
}
#endif

#endif /* SNIFFER_SLAVE_MONITOR_H */
