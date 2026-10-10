/**
 * [v0.1]
 ******************************************************************************
 * @file    uart_stream.c
 * @brief   Interrupt-free UART transport implementation (see header).
 *
 * TX path:  producer -> ring buffer -> DMA1 CH1 -> USART2_TX (PA2)
 *           uart_stream_poll() starts a DMA transfer over the largest
 *           contiguous chunk whenever the channel is idle and data waits.
 * RX path:  USART2_RX (PA3) -> DMA1 CH2, circular, into s_rx[] (fw 1.5).
            The 1-byte RDR overran whenever the main loop polled it less
            often than once per byte (87 us at 115200), which fw 1.4's
            slower capture loop did; DMA needs no CPU and no interrupt.
 ******************************************************************************
 */
#include "stm32c0xx.h"
#include "stm32c0xx_ll_bus.h"
#include "stm32c0xx_ll_gpio.h"
#include "stm32c0xx_ll_usart.h"
#include "stm32c0xx_ll_dma.h"
#include "stm32c0xx_ll_dmamux.h"
#include "stm32c0xx_ll_rcc.h"

#include "sniffer_config.h"
#include "uart_stream.h"

/* --------------------------------------------------------------------------
 * TX ring buffer
 * ------------------------------------------------------------------------ */
static uint8_t  s_ring[UART_TX_RING_SIZE];
static volatile uint32_t s_head;      /* producer index (next write)        */
static volatile uint32_t s_tail;      /* consumer index (next DMA read)     */
static uint32_t s_dma_len;            /* bytes in the in-flight DMA burst   */
static uint8_t  s_dma_busy;

/* RX circular buffer, written by DMA1 CH2; s_rx_rd is the reader index  */
static uint8_t  s_rx[UART_RX_DMA_SIZE];
static uint32_t s_rx_rd;

static inline uint32_t ring_used(void)
{
    const uint32_t h = s_head;
    const uint32_t t = s_tail;
    return (h >= t) ? (h - t) : (UART_TX_RING_SIZE - t + h);
}

uint32_t uart_stream_tx_free(void)
{
    /* one byte kept unused to distinguish full from empty */
    return UART_TX_RING_SIZE - 1U - ring_used();
}

/* --------------------------------------------------------------------------
 * Init
 * ------------------------------------------------------------------------ */
void uart_stream_init(void)
{
    s_head     = 0U;
    s_tail     = 0U;
    s_dma_len  = 0U;
    s_dma_busy = 0U;
    s_rx_rd    = 0U;

    /* Clocks */
    LL_IOP_GRP1_EnableClock(LL_IOP_GRP1_PERIPH_GPIOA);
    LL_APB1_GRP1_EnableClock(LL_APB1_GRP1_PERIPH_USART2);
    LL_AHB1_GRP1_EnableClock(LL_AHB1_GRP1_PERIPH_DMA1);

    /* PA2 = USART2_TX, PA3 = USART2_RX, both AF1 (Nucleo VCP default)      */
    LL_GPIO_SetPinMode(GPIOA, LL_GPIO_PIN_2, LL_GPIO_MODE_ALTERNATE);
    LL_GPIO_SetPinMode(GPIOA, LL_GPIO_PIN_3, LL_GPIO_MODE_ALTERNATE);
    LL_GPIO_SetAFPin_0_7(GPIOA, LL_GPIO_PIN_2, LL_GPIO_AF_1);
    LL_GPIO_SetAFPin_0_7(GPIOA, LL_GPIO_PIN_3, LL_GPIO_AF_1);
    LL_GPIO_SetPinSpeed(GPIOA, LL_GPIO_PIN_2, LL_GPIO_SPEED_FREQ_HIGH);
    LL_GPIO_SetPinPull(GPIOA, LL_GPIO_PIN_3, LL_GPIO_PULL_UP);

    /* USART2: 8N1 @ HOST_UART_BAUD, TX and RX DMA enabled                          */
    LL_USART_SetTransferDirection(USART2, LL_USART_DIRECTION_TX_RX);
    LL_USART_ConfigCharacter(USART2, LL_USART_DATAWIDTH_8B,
                             LL_USART_PARITY_NONE, LL_USART_STOPBITS_1);
    LL_USART_SetHWFlowCtrl(USART2, LL_USART_HWCONTROL_NONE);
    LL_USART_SetOverSampling(USART2, LL_USART_OVERSAMPLING_16);
    LL_USART_SetBaudRate(USART2, SYSCLK_HZ, LL_USART_PRESCALER_DIV1,
                         LL_USART_OVERSAMPLING_16, HOST_UART_BAUD);
    LL_USART_EnableDMAReq_TX(USART2);
    LL_USART_EnableDMAReq_RX(USART2);
    LL_USART_Enable(USART2);
    while ((LL_USART_IsActiveFlag_TEACK(USART2) == 0U) ||
           (LL_USART_IsActiveFlag_REACK(USART2) == 0U))
    {
        /* wait for USART ready */
    }

    /* DMA1 CH1 <- DMAMUX request USART2_TX, mem->periph, byte, minc        */
    LL_DMA_SetPeriphRequest(DMA1, LL_DMA_CHANNEL_1, LL_DMAMUX_REQ_USART2_TX);
    LL_DMA_SetDataTransferDirection(DMA1, LL_DMA_CHANNEL_1,
                                    LL_DMA_DIRECTION_MEMORY_TO_PERIPH);
    LL_DMA_SetChannelPriorityLevel(DMA1, LL_DMA_CHANNEL_1, LL_DMA_PRIORITY_LOW);
    LL_DMA_SetMode(DMA1, LL_DMA_CHANNEL_1, LL_DMA_MODE_NORMAL);
    LL_DMA_SetPeriphIncMode(DMA1, LL_DMA_CHANNEL_1, LL_DMA_PERIPH_NOINCREMENT);
    LL_DMA_SetMemoryIncMode(DMA1, LL_DMA_CHANNEL_1, LL_DMA_MEMORY_INCREMENT);
    LL_DMA_SetPeriphSize(DMA1, LL_DMA_CHANNEL_1, LL_DMA_PDATAALIGN_BYTE);
    LL_DMA_SetMemorySize(DMA1, LL_DMA_CHANNEL_1, LL_DMA_MDATAALIGN_BYTE);
    LL_DMA_SetPeriphAddress(DMA1, LL_DMA_CHANNEL_1,
                            LL_USART_DMA_GetRegAddr(USART2,
                                                    LL_USART_DMA_REG_DATA_TRANSMIT));

    /* DMA1 CH2 <- DMAMUX request USART2_RX, periph->mem, byte, minc,
     * circular: runs forever, the reader follows the write position.
     * Higher priority than TX so a TX burst never delays a received byte. */
    LL_DMA_SetPeriphRequest(DMA1, LL_DMA_CHANNEL_2, LL_DMAMUX_REQ_USART2_RX);
    LL_DMA_SetDataTransferDirection(DMA1, LL_DMA_CHANNEL_2,
                                    LL_DMA_DIRECTION_PERIPH_TO_MEMORY);
    LL_DMA_SetChannelPriorityLevel(DMA1, LL_DMA_CHANNEL_2, LL_DMA_PRIORITY_HIGH);
    LL_DMA_SetMode(DMA1, LL_DMA_CHANNEL_2, LL_DMA_MODE_CIRCULAR);
    LL_DMA_SetPeriphIncMode(DMA1, LL_DMA_CHANNEL_2, LL_DMA_PERIPH_NOINCREMENT);
    LL_DMA_SetMemoryIncMode(DMA1, LL_DMA_CHANNEL_2, LL_DMA_MEMORY_INCREMENT);
    LL_DMA_SetPeriphSize(DMA1, LL_DMA_CHANNEL_2, LL_DMA_PDATAALIGN_BYTE);
    LL_DMA_SetMemorySize(DMA1, LL_DMA_CHANNEL_2, LL_DMA_MDATAALIGN_BYTE);
    LL_DMA_SetPeriphAddress(DMA1, LL_DMA_CHANNEL_2,
                            LL_USART_DMA_GetRegAddr(USART2,
                                                    LL_USART_DMA_REG_DATA_RECEIVE));
    LL_DMA_SetMemoryAddress(DMA1, LL_DMA_CHANNEL_2, (uint32_t)&s_rx[0]);
    LL_DMA_SetDataLength(DMA1, LL_DMA_CHANNEL_2, UART_RX_DMA_SIZE);
    LL_DMA_EnableChannel(DMA1, LL_DMA_CHANNEL_2);
}

/* --------------------------------------------------------------------------
 * Producer
 * ------------------------------------------------------------------------ */
uint8_t uart_stream_write(const uint8_t *data, uint32_t len)
{
    uint32_t i;
    uint32_t head;

    if (len > uart_stream_tx_free())
    {
        return 0U;   /* caller counts the drop */
    }

    head = s_head;
    for (i = 0U; i < len; i++)
    {
        s_ring[head] = data[i];
        head++;
        if (head >= UART_TX_RING_SIZE)
        {
            head = 0U;
        }
    }
    s_head = head;
    return 1U;
}

/* --------------------------------------------------------------------------
 * TX pump - called from the main loop
 * ------------------------------------------------------------------------ */
void uart_stream_poll(void)
{
    if (s_dma_busy != 0U)
    {
        if (LL_DMA_IsActiveFlag_TC1(DMA1) != 0U)
        {
            LL_DMA_ClearFlag_TC1(DMA1);
            LL_DMA_ClearFlag_GI1(DMA1);
            LL_DMA_DisableChannel(DMA1, LL_DMA_CHANNEL_1);

            uint32_t tail = s_tail + s_dma_len;
            if (tail >= UART_TX_RING_SIZE)
            {
                tail -= UART_TX_RING_SIZE;
            }
            s_tail     = tail;
            s_dma_len  = 0U;
            s_dma_busy = 0U;
        }
        else
        {
            return;   /* burst still in flight */
        }
    }

    /* Start a new burst over the largest contiguous chunk                  */
    {
        const uint32_t head = s_head;
        const uint32_t tail = s_tail;
        uint32_t chunk;

        if (head == tail)
        {
            return;   /* ring empty */
        }
        chunk = (head > tail) ? (head - tail) : (UART_TX_RING_SIZE - tail);

        LL_DMA_SetMemoryAddress(DMA1, LL_DMA_CHANNEL_1,
                                (uint32_t)&s_ring[tail]);
        LL_DMA_SetDataLength(DMA1, LL_DMA_CHANNEL_1, chunk);
        s_dma_len  = chunk;
        s_dma_busy = 1U;
        LL_DMA_EnableChannel(DMA1, LL_DMA_CHANNEL_1);
    }
}

void uart_stream_flush(void)
{
    while ((ring_used() != 0U) || (s_dma_busy != 0U))
    {
        uart_stream_poll();
    }
    while (LL_USART_IsActiveFlag_TC(USART2) == 0U)
    {
        /* wait for the final byte to leave the shifter */
    }
}

/* --------------------------------------------------------------------------
 * RX
 * ------------------------------------------------------------------------ */
uint8_t uart_stream_read_byte(uint8_t *byte)
{
    /* DMA write position = size - remaining count (CNDTR counts down and
     * reloads in circular mode). If the host ever got more than
     * UART_RX_DMA_SIZE bytes ahead the oldest would be overwritten; the
     * parser's CRC then rejects the damaged command.                       */
    const uint32_t wr = UART_RX_DMA_SIZE -
                        LL_DMA_GetDataLength(DMA1, LL_DMA_CHANNEL_2);
    if (LL_USART_IsActiveFlag_ORE(USART2) != 0U)
    {
        LL_USART_ClearFlag_ORE(USART2);   /* cannot happen with DMA; harmless */
    }
    if ((wr % UART_RX_DMA_SIZE) == s_rx_rd)
    {
        return 0U;
    }
    *byte = s_rx[s_rx_rd];
    s_rx_rd++;
    if (s_rx_rd >= UART_RX_DMA_SIZE)
    {
        s_rx_rd = 0U;
    }
    return 1U;
}
