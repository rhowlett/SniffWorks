/**
 * [v0.1]
 * test_dut_timing.c - tier T1: TIMINGR calculator. The model is anchored
 * against the TIMINGR values STM32CubeMX 6.18 generated for this project
 * (100 kHz, rise 300 ns, fall 30 ns, 64 MHz kernel).
 */
#include <stdio.h>
#include <stdlib.h>
#include "dut_timing.h"

static int g_checks, g_fail;
#define CHECK(c, m) do { g_checks++; if (!(c)) { g_fail++; \
    printf("  FAIL: %s (%s:%d)\n", m, __FILE__, __LINE__); } } while (0)

static const dut_timing_env_t ENV = { 64000000U, 300U, 30U, 50U };

static int within_pct(uint32_t got, uint32_t want, double pct)
{
    const double d = (double)got - (double)want;
    return (d < 0 ? -d : d) <= want * pct / 100.0;
}

static void test_cubemx_anchor(void)
{
    printf("test_cubemx_anchor\n");
    const uint32_t mx_i2c1 = 0x40703444U;   /* firmware.ioc I2C1.Timing     */
    const uint32_t mx_i2c2 = 0x30803E58U;   /* firmware.ioc I2C2/3.Timing   */
    const uint32_t p1 = dut_timing_predict_hz(&ENV, mx_i2c1);
    const uint32_t p2 = dut_timing_predict_hz(&ENV, mx_i2c2);
    printf("  model on CubeMX values: %u Hz, %u Hz\n", (unsigned)p1, (unsigned)p2);
    CHECK(within_pct(p1, 100000U, 1.5), "CubeMX I2C1 TIMINGR predicts 100 kHz +-1.5 %");
    CHECK(within_pct(p2, 100000U, 1.5), "CubeMX I2C2 TIMINGR predicts 100 kHz +-1.5 %");
}

static void check_result(uint32_t hz, const dut_timing_t *t)
{
    char m[96];
    const int sm = hz <= 100000U;
    snprintf(m, sizeof m, "%u Hz: predicted within 2 %% (got %u)", (unsigned)hz,
             (unsigned)t->predicted_hz);
    CHECK(within_pct(t->predicted_hz, hz, 2.0), m);
    snprintf(m, sizeof m, "%u Hz: tLOW %u ns meets spec", (unsigned)hz, (unsigned)t->tlow_ns);
    CHECK(t->tlow_ns >= (sm ? 4700U : 1300U), m);
    snprintf(m, sizeof m, "%u Hz: tHIGH %u ns meets spec", (unsigned)hz, (unsigned)t->thigh_ns);
    CHECK(t->thigh_ns >= (sm ? 4000U : 600U), m);
    CHECK(t->sdadel <= 15U && t->scldel <= 15U, "SDADEL/SCLDEL fit 4 bits");
    CHECK(dut_timing_predict_hz(&ENV, t->timingr) == t->predicted_hz,
          "predict(timingr) == compute().predicted_hz");
    CHECK(((t->timingr >> 28) & 0xFU) == t->presc && (t->timingr & 0xFFU) == t->scll &&
          ((t->timingr >> 8) & 0xFFU) == t->sclh && ((t->timingr >> 16) & 0xFU) == t->sdadel &&
          ((t->timingr >> 20) & 0xFU) == t->scldel, "fields packed into TIMINGR");
}

static void test_standard_speeds(void)
{
    printf("test_standard_speeds\n");
    dut_timing_t t;
    CHECK(dut_timing_compute(&ENV, 100000U, &t) == 0, "100 kHz computes");
    printf("  100k: TIMINGR=0x%08X pred=%u\n", (unsigned)t.timingr, (unsigned)t.predicted_hz);
    check_result(100000U, &t);
    CHECK(dut_timing_compute(&ENV, 400000U, &t) == 0, "400 kHz computes");
    printf("  400k: TIMINGR=0x%08X pred=%u\n", (unsigned)t.timingr, (unsigned)t.predicted_hz);
    check_result(400000U, &t);
}

static void test_sweep(void)
{
    printf("test_sweep 10k..400k\n");
    for (uint32_t hz = 10000U; hz <= 400000U; hz += 10000U)
    {
        dut_timing_t t;
        char m[64];
        snprintf(m, sizeof m, "%u Hz computes", (unsigned)hz);
        const int rc = dut_timing_compute(&ENV, hz, &t);
        CHECK(rc == 0, m);
        if (rc == 0) { check_result(hz, &t); }
    }
}

static void test_limits(void)
{
    printf("test_limits\n");
    dut_timing_t t;
    CHECK(dut_timing_compute(&ENV, 999U, &t) == -1, "< 1 kHz rejected (-1)");
    CHECK(dut_timing_compute(&ENV, 1000001U, &t) == -1, "> 1 MHz rejected (-1)");
    CHECK(dut_timing_compute(&ENV, 5000U, &t) == -2,
          "5 kHz: SCLL/SCLH overflow at max prescaler (-2)");
    CHECK(dut_timing_compute(&ENV, 1000000U, &t) == -2,
          "1 MHz with 300 ns rise is infeasible (-2)");
    CHECK(dut_timing_compute(0, 100000U, &t) == -1, "NULL env rejected");
}

int main(void)
{
    printf("=== dut_timing host tests ===\n");
    test_cubemx_anchor();
    test_standard_speeds();
    test_sweep();
    test_limits();
    printf("=== %d checks, %d failures ===\n", g_checks, g_fail);
    return g_fail ? EXIT_FAILURE : EXIT_SUCCESS;
}
