# =============================================================================
# [v0.1]
# embedded/tests/host - host-compiled unit tests for the firmware's pure
# modules (i2c_bitbang_decoder, frame_protocol, edge_ring).
#
#   make          build both test binaries
#   make test     build + run
#   make clean
#
# The same C files that run on the STM32 are compiled here unmodified -
# they contain no hardware access.
# =============================================================================

FW_DIR   := ../../sniffer_nucleoC0_fw
CC       := gcc
CFLAGS   := -std=gnu11 -O1 -g -Wall -Wextra -Wshadow \
            -fsanitize=address,undefined \
            -I$(FW_DIR)/Core/Inc -I.

BUILD    := build

TESTS    := $(BUILD)/test_i2c_decoder $(BUILD)/test_frame_protocol \
            $(BUILD)/test_edge_ring

.PHONY: all test clean

all: $(TESTS)

$(BUILD)/test_i2c_decoder: test_i2c_decoder.c waveform_gen.c \
                           $(FW_DIR)/Core/Src/i2c_bitbang_decoder.c
	@mkdir -p $(BUILD)
	$(CC) $(CFLAGS) $^ -o $@

$(BUILD)/test_frame_protocol: test_frame_protocol.c \
                              $(FW_DIR)/Core/Src/frame_protocol.c \
                              $(FW_DIR)/Core/Src/i2c_bitbang_decoder.c
	@mkdir -p $(BUILD)
	$(CC) $(CFLAGS) $^ -o $@

$(BUILD)/test_edge_ring: test_edge_ring.c waveform_gen.c \
                         $(FW_DIR)/Core/Src/i2c_bitbang_decoder.c
	@mkdir -p $(BUILD)
	$(CC) $(CFLAGS) $^ -o $@

test: all
	@echo "--------------------------------------------------"
	$(BUILD)/test_i2c_decoder
	@echo "--------------------------------------------------"
	$(BUILD)/test_frame_protocol
	@echo "--------------------------------------------------"
	$(BUILD)/test_edge_ring
	@echo "--------------------------------------------------"
	@echo "ALL HOST TESTS PASSED"

clean:
	rm -rf $(BUILD)
