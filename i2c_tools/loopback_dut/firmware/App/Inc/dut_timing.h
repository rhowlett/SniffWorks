/**
 * [v0.1]
 * @file    dut_timing.h
 * @brief   STM32 I2C v2 TIMINGR calculator for an arbitrary SCL frequency.
 *          Pure C (no HAL); unit-tested in loopback_dut/tests/host.
 *
 * Model (RM0481 "I2C timings", master mode):
 *   t_SCL  = t_SYNC1 + t_SYNC2 + (SCLL + 1 + SCLH + 1) * t_PRESC
 *   t_SYNC1 ~= t_fall + t_AF + 3 * t_I2CCLK      (SCL low  detection)
 *   t_SYNC2 ~= t_rise + t_AF + 3 * t_I2CCLK      (SCL high detection)
 * The synchronisation terms are typical, not guaranteed, so the result is
 * a PREDICTION; the sniffer's measured scl_hz is the ground truth.
 *
 * Constraints enforced (I2C-bus spec UM10204 Table 10, + SMBus hold):
 *   <= 100 kHz  Sm : tLOW >= 4.7 us, tHIGH >= 4.0 us, tSU;DAT >= 250 ns
 *   <= 400 kHz  Fm : tLOW >= 1.3 us, tHIGH >= 0.6 us, tSU;DAT >= 100 ns
 *   <= 1 MHz    Fm+: tLOW >= 0.5 us, tHIGH >= 0.26 us, tSU;DAT >= 50 ns
 *   data hold targets 300 ns (SMBus tHD;DAT min) where the prescaler allows.
 * The smallest prescaler that satisfies every field range is chosen, which
 * gives the finest frequency resolution.
 */
#ifndef DUT_TIMING_H
#define DUT_TIMING_H

#include <stdint.h>

typedef struct
{
    uint32_t timingr;       /* value for I2C_TIMINGR                        */
    uint8_t  presc;
    uint8_t  scll;
    uint8_t  sclh;
    uint8_t  sdadel;
    uint8_t  scldel;
    uint32_t predicted_hz;  /* model's SCL for this TIMINGR                  */
    uint32_t tlow_ns;       /* (SCLL+1) * t_PRESC                            */
    uint32_t thigh_ns;      /* (SCLH+1) * t_PRESC                            */
} dut_timing_t;

typedef struct
{
    uint32_t kernel_hz;     /* I2C kernel clock                               */
    uint32_t rise_ns;
    uint32_t fall_ns;
    uint32_t taf_ns;        /* analog filter delay                            */
} dut_timing_env_t;

/** 0 on success; -1 bad argument / unsupported speed (> 1 MHz, < 1 kHz);
 *  -2 no prescaler satisfies the constraints (e.g. rise too slow). */
int dut_timing_compute(const dut_timing_env_t *env, uint32_t scl_hz,
                       dut_timing_t *out);

/** Predicted SCL for an existing TIMINGR value (same model). */
uint32_t dut_timing_predict_hz(const dut_timing_env_t *env, uint32_t timingr);

#endif /* DUT_TIMING_H */
