# =============================================================================
# [v0.1]
# loopback_dut/tests/host - host-compiled unit tests (tier T1, no hardware) for
# the DUT firmware's pure modules: dut_regmap, dut_timing, dut_proto.
#
#   make          build
#   make test     build + run
#   make clean
#
# The same App/Src files that run on the STM32H533 compile here unmodified.
# =============================================================================
FW_DIR := ../../firmware
CC     := gcc
CFLAGS := -std=gnu11 -O1 -g -Wall -Wextra -Wshadow -Werror \
          -fsanitize=address,undefined -I$(FW_DIR)/App/Inc
BUILD  := build
TESTS  := $(BUILD)/test_dut_regmap $(BUILD)/test_dut_timing $(BUILD)/test_dut_proto

.PHONY: all test clean
all: $(TESTS)

$(BUILD)/test_dut_regmap: test_dut_regmap.c $(FW_DIR)/App/Src/dut_regmap.c
	@mkdir -p $(BUILD)
	$(CC) $(CFLAGS) $^ -o $@

$(BUILD)/test_dut_timing: test_dut_timing.c $(FW_DIR)/App/Src/dut_timing.c
	@mkdir -p $(BUILD)
	$(CC) $(CFLAGS) $^ -o $@

$(BUILD)/test_dut_proto: test_dut_proto.c $(FW_DIR)/App/Src/dut_proto.c \
                         $(FW_DIR)/App/Src/dut_regmap.c
	@mkdir -p $(BUILD)
	$(CC) $(CFLAGS) $^ -o $@

test: all
	@set -e; for t in $(TESTS); do echo "--- $$t"; $$t; done; \
	echo "ALL LOOPBACK DUT HOST TESTS PASSED"

clean:
	rm -rf $(BUILD)
