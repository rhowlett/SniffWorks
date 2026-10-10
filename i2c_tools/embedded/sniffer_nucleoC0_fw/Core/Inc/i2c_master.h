/* ==========================================================================
 * i2c_master.h
 * Active I2C master for SNIFF_MODE_MASTER (replay / programmer transport).
 *
 * Polled LL driver on I2C1 (same PA9=SCL / PA10=SDA pins as the sniffer,
 * now in AF6 open-drain instead of inputs). Executes the variable-length
 * host commands CMD_I2C_WRITE / CMD_I2C_WRITE_READ / CMD_I2C_READ /
 * CMD_SET_BUS_SPEED and reports each bus phase as a standard TXN frame -
 * a master-issued transaction and a sniffed one are the same record, so the
 * host's log/decode stack is reused unchanged.
 *
 * Result signaling in TXN flags: TXN_FLAG_NAK for an address/data NACK,
 * TXN_FLAG_TIMEOUT if the transfer exceeded MASTER_TIMEOUT_US (bus stuck,
 * no pull-ups, etc.). Bus errors (BERR/ARLO) additionally raise
 * ERR_CODE_BUS_ERROR.
 * ========================================================================== */
#ifndef I2C_MASTER_H
#define I2C_MASTER_H

#include <stdint.h>

void i2c_master_init(uint32_t (*now_us)(void)); /* GPIO + I2C1 @ default    */
void i2c_master_set_timing(uint32_t timingr);

/* Execute one parsed host command (cmd + payload from cmd_parser_t).
 * Emits TXN/STATUS/ERROR frames via uart_stream as side effects.           */
void i2c_master_exec(uint8_t cmd, const uint8_t *payload, uint8_t len);

uint32_t i2c_master_txn_count(void);        /* for STATUS.captured          */
uint32_t i2c_master_error_count(void);      /* for STATUS.errors            */

#endif /* I2C_MASTER_H */
