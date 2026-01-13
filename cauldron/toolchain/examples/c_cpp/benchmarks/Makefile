FB_CC ?= fb-cc
OUT_DIR ?= out
RAM_COUNT ?= 3
FB_FLAGS ?= -DFB_HEAP_SEGMENT=1 -DFB_HEAP_SEGMENT_COUNT=1 -DFB_GRAPH_SEGMENT=2 -DFB_ARB_SEGMENT=3

SOURCES = \
	bench_putchar.c \
	bench_write.c \
	bench_exit.c \
	bench_yield.c \
	bench_debug_log.c \
	bench_matmul.c \
	bench_rmsnorm.c \
	bench_softmax.c \
	bench_silu.c \
	bench_rope.c \
	bench_matmul_q8.c \
	bench_matmul_q8_partial.c \
	bench_accum.c \
	bench_read_f32.c \
	bench_write_f32.c \
	bench_memcpy_f32.c \
	bench_argmax_partial.c \
	bench_matmul_i8_i32.c \
	bench_matmul_i8_i32_partial.c \
	bench_softmax_i32.c \
	bench_dot_i32.c \
	bench_weighted_sum_i32.c \
	bench_argmax_i32_partial.c \
	bench_softmax_i32_f32.c \
	bench_silu_mul_i32.c \
	bench_rmsnorm_i32.c \
	bench_matmul_i8_i8.c \
	bench_matmul_i8_i8_partial.c \
	bench_matmul_i8_i8_argmax.c \
	bench_matmul_i8_i8_qkv.c \
	bench_matmul_i8_i8_w1w3.c \
	bench_matmul_i8_i8_w1w3_silu.c \
	bench_dot_i8.c \
	bench_vec_add_i8.c \
	bench_activation.c \
	bench_graph_search.c \
	bench_graph_search_alt.c \
	bench_arb_search.c \
	bench_arb_score.c \
	bench_aggregate.c \
	bench_quantum_op.c

BINS = $(SOURCES:%.c=$(OUT_DIR)/%.elf)

all: $(BINS)

$(OUT_DIR):
	@mkdir -p $(OUT_DIR)

$(OUT_DIR)/%.elf: %.c bench_common.h | $(OUT_DIR)
	$(FB_CC) $(FB_FLAGS) $< -o $@

run-local: $(BINS)
	@set -e; \
	for bin in $(BINS); do \
		echo "==> $$bin"; \
		frostbite-run --ram-count $(RAM_COUNT) $$bin; \
	done

run-onchain: $(BINS)
	@if [ -z "$$FROSTBITE_PROGRAM_ID" ]; then \
		echo "FROSTBITE_PROGRAM_ID not set"; \
		exit 1; \
	fi
	@set -e; \
	for bin in $(BINS); do \
		echo "==> $$bin"; \
		frostbite-run-onchain --program-id $$FROSTBITE_PROGRAM_ID --ram-count $(RAM_COUNT) $$bin; \
	done

clean:
	rm -rf $(OUT_DIR)
