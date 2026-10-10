# =============================================================================
# sniffer_nucleoC0_fw - Makefile
#
# Command-line build equivalent to the STM32CubeIDE project (same sources,
# defines, and flags). Requires arm-none-eabi-gcc.
#
#   make            release build -> build/sniffer_nucleoC0_fw.{elf,hex,bin}
#   make DEBUG=1    debug build (-Og -g3)
#   make clean
#
# Mode/baud overrides (see Core/Inc/sniffer_config.h):
#   make EXTRA_DEFS='-DSNIFF_MODE=SNIFF_MODE_SLAVE_MON -DHOST_UART_BAUD=921600'
# =============================================================================

TARGET      := sniffer_nucleoC0_fw
BUILD_DIR   := build

PREFIX      := arm-none-eabi-
CC          := $(PREFIX)gcc
AS          := $(PREFIX)gcc -x assembler-with-cpp
OBJCOPY     := $(PREFIX)objcopy
SIZE        := $(PREFIX)size

# -----------------------------------------------------------------------------
# Sources
# -----------------------------------------------------------------------------
C_SOURCES := \
  Core/Src/main.c \
  Core/Src/i2c_bitbang_decoder.c \
  Core/Src/frame_protocol.c \
  Core/Src/uart_stream.c \
  Core/Src/sniffer_slave_monitor.c \
Core/Src/i2c_master.c \
  Core/Src/system_stm32c0xx.c \
  Core/Src/syscalls.c \
  Core/Src/sysmem.c \
  Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_ll_gpio.c \
  Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_ll_usart.c \
  Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_ll_dma.c \
  Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_ll_i2c.c \
  Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_ll_tim.c \
  Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_ll_rcc.c \
  Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_ll_utils.c \
  Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_ll_exti.c

ASM_SOURCES := Core/Startup/startup_stm32c031xx.s

C_INCLUDES := \
  -ICore/Inc \
  -IDrivers/CMSIS/Include \
  -IDrivers/CMSIS/Device/ST/STM32C0xx/Include \
  -IDrivers/STM32C0xx_HAL_Driver/Inc

C_DEFS := -DSTM32C031xx -DUSE_FULL_LL_DRIVER -DHSE_VALUE=48000000 $(EXTRA_DEFS)

# -----------------------------------------------------------------------------
# Flags (mirror the CubeIDE project settings)
# -----------------------------------------------------------------------------
MCU    := -mcpu=cortex-m0plus -mthumb -mfloat-abi=soft

ifeq ($(DEBUG),1)
OPT    := -Og -g3
else
OPT    := -O2 -g
endif

CFLAGS := $(MCU) $(C_DEFS) $(C_INCLUDES) $(OPT) \
          -Wall -Wextra -Wshadow -Wundef \
          -ffunction-sections -fdata-sections -fstack-usage \
          -std=gnu11 -MMD -MP

LDSCRIPT := STM32C031C6TX_FLASH.ld
LDFLAGS  := $(MCU) -T$(LDSCRIPT) --specs=nano.specs --specs=nosys.specs \
            -Wl,-Map=$(BUILD_DIR)/$(TARGET).map,--cref -Wl,--gc-sections \
            -static -Wl,--start-group -lc -lm -Wl,--end-group

# -----------------------------------------------------------------------------
# Build rules
# -----------------------------------------------------------------------------
OBJECTS := $(addprefix $(BUILD_DIR)/,$(C_SOURCES:.c=.o))
OBJECTS += $(addprefix $(BUILD_DIR)/,$(ASM_SOURCES:.s=.o))

.PHONY: all clean size

all: $(BUILD_DIR)/$(TARGET).elf $(BUILD_DIR)/$(TARGET).hex $(BUILD_DIR)/$(TARGET).bin size

$(BUILD_DIR)/%.o: %.c
	@mkdir -p $(dir $@)
	$(CC) -c $(CFLAGS) $< -o $@

$(BUILD_DIR)/%.o: %.s
	@mkdir -p $(dir $@)
	$(AS) -c $(MCU) $< -o $@

$(BUILD_DIR)/$(TARGET).elf: $(OBJECTS)
	$(CC) $(OBJECTS) $(LDFLAGS) -o $@

$(BUILD_DIR)/$(TARGET).hex: $(BUILD_DIR)/$(TARGET).elf
	$(OBJCOPY) -O ihex $< $@

$(BUILD_DIR)/$(TARGET).bin: $(BUILD_DIR)/$(TARGET).elf
	$(OBJCOPY) -O binary -S $< $@

size: $(BUILD_DIR)/$(TARGET).elf
	$(SIZE) $<

clean:
	rm -rf $(BUILD_DIR)

-include $(OBJECTS:.o=.d)
