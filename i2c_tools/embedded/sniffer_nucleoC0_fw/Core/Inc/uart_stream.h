/**
 * [v0.1]
 ******************************************************************************
 * @file    uart_stream.h
 * @brief   Interrupt-free UART transport: DMA-driven TX ring buffer plus
 *          DMA-driven circular RX (fw 1.5), on USART2 (ST-LINK Virtual COM port).
 *
 *          No interrupts are used anywhere in this firmware so the bit-bang
 *          capture loop keeps deterministic, jitter-free timing. The main
 *          loop calls uart_stream_poll() to advance the DMA machinery.
 ******************************************************************************
 */
#ifndef UART_STREAM_H
#define UART_STREAM_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/** Configure GPIO (PA2/PA3 AF1), USART2 @ HOST_UART_BAUD, DMA1 CH1 (TX) and
 *  CH2 (RX, circular) via DMAMUX. */
void uart_stream_init(void);

/**
 * Queue len bytes for transmission.
 * @return 1 on success, 0 if the ring lacks space (frame dropped - the
 *         caller must count it; never blocks).
 */
uint8_t uart_stream_write(const uint8_t *data, uint32_t len);

/** Advance TX: start/complete DMA transfers. Call frequently from the loop. */
void uart_stream_poll(void);

/**
 * Non-blocking receive from the RX DMA buffer; may be called as rarely as
 * once per UART_RX_DMA_SIZE byte times without loss.
 * @return 1 and stores the byte if one was available, else 0.
 */
uint8_t uart_stream_read_byte(uint8_t *byte);

/** Bytes free in the TX ring (diagnostics). */
uint32_t uart_stream_tx_free(void);

/** Block (polling DMA) until the TX ring is empty. Boot/shutdown use only. */
void uart_stream_flush(void);

#ifdef __cplusplus
}
#endif

#endif /* UART_STREAM_H */
