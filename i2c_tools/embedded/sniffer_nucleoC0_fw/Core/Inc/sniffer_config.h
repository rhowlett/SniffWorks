/**
 * [v0.4]
 ******************************************************************************
 * @file    sniffer_config.h
 * @brief   Central compile-time configuration for the NUCLEO-C031C6 I2C
 *          sniffer firmware. ALL user-selectable options live here.
 ******************************************************************************
 * Target board : ST NUCLEO-C031C6 (MB1717), STM32C031C6T6
 *                Cortex-M0+, 48 MHz, 32 KB flash, 12 KB RAM
 *
 * Wiring (Arduino headers, per UM2953 Rev 2):
 *   SCL -> D8  (CN5 pin 1)  = PA9
 *   SDA -> D2  (CN9 pin 3)  = PA10
 *   GND -> any GND
 *
 * Host link: USART2 (PA2/PA3) through the on-board ST-LINK Virtual COM port.
 ******************************************************************************
 */
#ifndef SNIFFER_CONFIG_H
#define SNIFFER_CONFIG_H

/* ---------------------------------------------------------------------------
 * Capture mode selection
 * ---------------------------------------------------------------------------
 * SNIFF_MODE_BITBANG (default, recommended):
 *   Pure GPIO sampling of SCL/SDA in a tight, interrupt-free polling loop.
 *   - 100% passive: never drives or ACKs the bus.
 *   - Captures everything: writes, reads (with data), NAKs, restarts.
 *   - Speed-agnostic: no bus-speed configuration needed (the "Auto" mode);
 *     the measured bus frequency is reported in STATUS frames.
 *   - Verified budget: 100 kHz standard mode with ample margin.
 *     400 kHz fast mode is best-effort (see docs/PROTOCOL.md, "Timing").
 *
 * SNIFF_MODE_SLAVE_MON (experimental / limited):
 *   Uses the I2C1 peripheral in slave mode with OA2 address mask = match-all.
 *   - Hardware-assisted: near-zero CPU cost per byte, robust at 400 kHz.
 *   - LIMITATIONS (inherent to the peripheral, not fixable in firmware):
 *       * Read-transaction payloads canNOT be captured (only addr + dir).
 *         The peripheral preloads 0xFF so it never pulls SDA low, remaining
 *         electrically transparent while the real slave drives the data.
 *       * The peripheral hardware-ACKs every matched address, which can mask
 *         a NAK from an absent/busy slave (mildly intrusive on the bus).
 */
#define SNIFF_MODE_BITBANG      1
#define SNIFF_MODE_SLAVE_MON    2
#define SNIFF_MODE_MASTER       3   /* active I2C master (replay/programmer) */

#ifndef SNIFF_MODE
#define SNIFF_MODE              SNIFF_MODE_BITBANG
#endif

/* --------------------------------------------------------------------------
 * Target board [XREF: board-select]
 * BOARD_NUCLEO_C031C6 (default): NUCLEO-C031C6 dev board, ST-LINK VCP.
 * BOARD_ION_C0: the planned standalone STM32C0 "ion" board with a USB-UART
 *   bridge. Pin map is PROVISIONAL (identical to the Nucleo until the board
 *   is finalized) - update the pin block below when hardware lands.
 * Select with: make EXTRA_DEFS='-DBOARD=BOARD_ION_C0'
 * ------------------------------------------------------------------------ */
#define BOARD_NUCLEO_C031C6     1
#define BOARD_ION_C0            2

#ifndef BOARD
#define BOARD                   BOARD_NUCLEO_C031C6
#endif
#if (BOARD != BOARD_NUCLEO_C031C6) && (BOARD != BOARD_ION_C0)
#error "BOARD must be BOARD_NUCLEO_C031C6 or BOARD_ION_C0"
#endif

/* ---------------------------------------------------------------------------
 * Sniff pins  (bit-bang mode may use any GPIOs on the same port;
 *              slave-monitor mode requires pins with the I2C1 AF)
 * PA9 / PA10 carry I2C1_SCL / I2C1_SDA on AF6 (STM32C031 datasheet, Table
 * "Alternate functions"), so both modes work on the defaults below.
 * ------------------------------------------------------------------------- */
#define SNIFF_GPIO_PORT         GPIOA
#define SNIFF_GPIO_CLK_EN()     (RCC->IOPENR |= RCC_IOPENR_GPIOAEN)
#define SNIFF_SCL_PIN           9U       /* PA9  = Arduino D8  */
#define SNIFF_SDA_PIN           10U      /* PA10 = Arduino D2  */
#define SNIFF_I2C_AF            6U       /* AF6 = I2C1 on PA9/PA10 */

/* ---------------------------------------------------------------------------
 * Host UART (ST-LINK VCP = USART2 on PA2/PA3, AF1)
 * 115200 is the project default. A saturated 100 kHz I2C bus can exceed
 * 115200 baud once framed; the TX ring absorbs bursts and the firmware
 * counts dropped frames (reported in STATUS). For sustained heavy traffic
 * raise this to 921600 - the ST-LINK VCP supports it.
 * ------------------------------------------------------------------------- */
#ifndef HOST_UART_BAUD
#define HOST_UART_BAUD          115200U
#endif

/* ---------------------------------------------------------------------------
 * Bit-bang sampling by edge interrupt (fw 1.6, owner decision 2026-10-05,
 * review B30/B31). EXTI fires on every SCL/SDA edge (PA9/PA10, EXTI4_15);
 * the ISR stores (TIM3 us, lines) into a RAM edge ring and the main loop
 * decodes from the ring. Sampling no longer waits for decoding: on the rig
 * a polled decode pass took 3-6 us against a 4.9 us SCL high at 100 kHz,
 * so whole clock pulses went unseen (embedded/docs/B30_B31_investigation.md
 * §1.4). This is the firmware's only interrupt. Set 0 to rebuild the fw 1.5
 * polled loop for comparison.
 * ------------------------------------------------------------------------- */
#ifndef SNIFF_EDGE_IRQ
#define SNIFF_EDGE_IRQ          1
#endif
#define EDGE_RING_SIZE          1024U    /* edges (power of two), 3 B each:  */
                                         /* ~35 bytes of 100 kHz backlog     */

/* ---------------------------------------------------------------------------
 * Buffers (12 KB RAM total on the C031C6 - keep an eye on the .map file)
 * ------------------------------------------------------------------------- */
#if (SNIFF_MODE == SNIFF_MODE_BITBANG) && (SNIFF_EDGE_IRQ != 0)
#define UART_TX_RING_SIZE       4096U    /* 2 KB given to the edge ring      */
#else
#define UART_TX_RING_SIZE       6144U    /* bytes; power-of-two NOT required */
#endif
#define UART_RX_DMA_SIZE        256U     /* host->probe circular DMA buffer: */
                                         /* 22 ms at 115200, > the longest  */
                                         /* upkeep deferral (fw 1.5)        */
#define TXN_MAX_DATA            64U      /* max captured data bytes per txn  */
#define I2C_DEC_RING_DEPTH      8U       /* decoder record ring (one slot is */
                                         /* always the record in assembly)   */

/* ---------------------------------------------------------------------------
 * SCL measurement (bit-bang mode). A phase reports scl_hz only when at least
 * this many un-stretched SCL rise-to-rise periods were seen; below that the
 * 1 us timestamp quantisation dominates. Raise it to trade short phases
 * (address-only probes = 8 periods) for accuracy.
 * ------------------------------------------------------------------------- */
#ifndef I2C_DEC_SCL_MIN_PERIODS
#define I2C_DEC_SCL_MIN_PERIODS 4U
#endif

/* ---------------------------------------------------------------------------
 * Sampler diagnostics (fw 1.4, bit-bang mode). TIM14 free-runs at SYSCLK
 * (48 MHz, 20.8 ns tick, 16-bit = 1.365 ms wrap) and measures, while a
 * transaction is open: the longest gap between two samples, the narrowest
 * SCL high / low pulse, and the same for phases flagged FRAMING. Reported
 * as a trailing block on STATUS (PROTOCOL.md 1.2.1).
 * fw 1.5: OFF by default. On hardware (2026-10-05) it slowed the capture
 * loop so much that 100 kHz decoding collapsed (address 0x00, no data), so
 * its numbers describe a different loop from the one under test. Use
 * SNIFF_TRACE + a logic analyser instead.
 * ------------------------------------------------------------------------- */
#ifndef SNIFF_DIAG
#define SNIFF_DIAG              0
#endif
#define DIAG_TICKS_PER_US       (SYSCLK_HZ / 1000000U)

/* ---------------------------------------------------------------------------
 * B30 mitigation: skip the every-64-iterations UART upkeep (and the 1 Hz
 * STATUS it sends) while a bus transaction is open, so nothing but sampling
 * runs between START and STOP. Upkeep is forced after UPKEEP_MAX_DEFER_US
 * of continuous transaction (a stuck bus must not starve the host link).
 * fw 1.5: OFF by default. On hardware (2026-10-05) the per-iteration hold
 * check collapsed 100 kHz decoding just like SNIFF_DIAG did.
 * ------------------------------------------------------------------------- */
/* Flash prefetch + instruction cache (fw 1.5). Speeds up the polled capture
 * loop; set 0 only to reproduce fw <= 1.4 timing.                          */
/* Timing trace pins for a logic analyser (fw 1.5, investigation only;
 * bit-bang mode). Free pins on the Arduino header, push-pull outputs:
 *   PA1 (A1) BUSY: high while the upkeep slot or a frame flush runs.
 *   PA0 (A0) LOOP: toggles once per capture-loop iteration (level 2 only;
 *            costs ~4 cycles per iteration, so it slightly slows the loop).
 * 0 = off (release); 1 = BUSY only (no per-iteration cost); 2 = BUSY + LOOP. */
#ifndef SNIFF_TRACE
#define SNIFF_TRACE             0
#endif

/* Unsolicited STATUS period while capturing (us).                          */
#ifndef STATUS_PERIOD_US
#define STATUS_PERIOD_US        1000000U
#endif

#ifndef SNIFF_FLASH_ACCEL
#define SNIFF_FLASH_ACCEL       1
#endif

#ifndef SNIFF_DEFER_UPKEEP
#define SNIFF_DEFER_UPKEEP      0
#endif
#define UPKEEP_MAX_DEFER_US     20000U
/* RX DMA must hold every byte that can arrive while upkeep is held off   */
#if ((UART_RX_DMA_SIZE * 10U * 1000000U) / HOST_UART_BAUD) <= UPKEEP_MAX_DEFER_US
#error "UART_RX_DMA_SIZE too small for UPKEEP_MAX_DEFER_US at HOST_UART_BAUD"
#endif

/* ---------------------------------------------------------------------------
 * Firmware identity (reported in HELLO / STATUS frames)
 * ------------------------------------------------------------------------- */
#define FW_VERSION_MAJOR        1U
#define FW_VERSION_MINOR        6U   /* 1.2: zero-copy ring (Sr bit-slip fix), */
                                     /*      FRAMING flag, missed-START count */
                                     /* 1.3: per-transaction SCL measurement  */
                                     /*      (TXN trailing u32 scl_hz)        */
                                     /* 1.4: sampler diagnostics in STATUS,   */
                                     /*      table CRC, upkeep deferred while */
                                     /*      a transaction is open (B30)      */
                                     /* 1.5: host RX by circular DMA; 1.4's  */
                                     /*      slower loop overran the 1-byte  */
                                     /*      RDR and lost commands mid-capture*/
                                     /* 1.6: bit-bang sampling by EXTI edge  */
                                     /*      ISR + edge ring (B30/B31)       */
#define FRAME_PROTOCOL_VERSION  1U

/* ---------------------------------------------------------------------------
 * System clock
 * ------------------------------------------------------------------------- */
#define SYSCLK_HZ               48000000U

/* Sanity checks ----------------------------------------------------------- */
#if (SNIFF_MODE != SNIFF_MODE_BITBANG) && (SNIFF_MODE != SNIFF_MODE_SLAVE_MON) \
    && (SNIFF_MODE != SNIFF_MODE_MASTER)
#error "SNIFF_MODE must be SNIFF_MODE_BITBANG, SNIFF_MODE_SLAVE_MON, or SNIFF_MODE_MASTER"
#endif

/* --------------------------------------------------------------------------
 * Master-mode bus timing (SNIFF_MODE_MASTER only). TIMINGR values verified
 * on hardware at PCLK = 48 MHz (from Test_STM32C031_BQ76905).
 * ------------------------------------------------------------------------ */
#define MASTER_TIMING_100K      0xB0421013UL
#define MASTER_TIMING_400K      0x10530F20UL
#ifndef MASTER_TIMING_DEFAULT
#define MASTER_TIMING_DEFAULT   MASTER_TIMING_100K
#endif
#define MASTER_TIMEOUT_US       25000U   /* per-transfer budget              */
#if (I2C_DEC_RING_DEPTH < 2U) || (I2C_DEC_RING_DEPTH > 255U)
#error "I2C_DEC_RING_DEPTH must be 2..255"
#endif
#if (TXN_MAX_DATA > 255U)
#error "TXN_MAX_DATA must fit in the u8 length field of the TXN frame"
#endif

#endif /* SNIFFER_CONFIG_H */
