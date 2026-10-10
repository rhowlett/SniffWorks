/**
 * [v0.1]
 * @file    dut_timing.c
 * @brief   TIMINGR calculator (see dut_timing.h for the model and limits).
 *          All arithmetic in picoseconds, 64-bit.
 */
#include "dut_timing.h"

#define PS_PER_NS   1000ULL
#define PS_PER_S    1000000000000ULL

static uint64_t div_round(uint64_t n, uint64_t d) { return (n + d / 2U) / d; }
static uint64_t div_ceil(uint64_t n, uint64_t d)  { return (n + d - 1U) / d; }

/* t_SYNC1 + t_SYNC2 in ps */
static uint64_t sync_ps(const dut_timing_env_t *env, uint64_t tk)
{
    return ((uint64_t)env->fall_ns + env->rise_ns + 2ULL * env->taf_ns) * PS_PER_NS
           + 6ULL * tk;
}

uint32_t dut_timing_predict_hz(const dut_timing_env_t *env, uint32_t timingr)
{
    if ((env == 0) || (env->kernel_hz == 0U))
    {
        return 0U;
    }
    const uint64_t tk    = PS_PER_S / env->kernel_hz;
    const uint64_t presc = (timingr >> 28) & 0xFU;
    const uint64_t sclh  = (timingr >> 8) & 0xFFU;
    const uint64_t scll  = timingr & 0xFFU;
    const uint64_t tp    = (presc + 1U) * tk;
    const uint64_t t_scl = (scll + 1U + sclh + 1U) * tp + sync_ps(env, tk);
    return (uint32_t)div_round(PS_PER_S, t_scl);
}

int dut_timing_compute(const dut_timing_env_t *env, uint32_t scl_hz,
                       dut_timing_t *out)
{
    if ((env == 0) || (out == 0) || (env->kernel_hz == 0U) ||
        (scl_hz < 1000U) || (scl_hz > 1000000U))
    {
        return -1;
    }

    uint64_t tlow_min, thigh_min, tsu_min, low_frac_x1000;
    if (scl_hz <= 100000U)
    {
        tlow_min = 4700000U; thigh_min = 4000000U; tsu_min = 250000U;
        low_frac_x1000 = 500U;
    }
    else if (scl_hz <= 400000U)
    {
        tlow_min = 1300000U; thigh_min = 600000U;  tsu_min = 100000U;
        low_frac_x1000 = 600U;
    }
    else
    {
        tlow_min = 500000U;  thigh_min = 260000U;  tsu_min = 50000U;
        low_frac_x1000 = 600U;
    }
    const uint64_t thd_target = 300000U;               /* SMBus tHD;DAT     */

    const uint64_t tk     = PS_PER_S / env->kernel_hz;
    const uint64_t t_scl  = div_round(PS_PER_S, scl_hz);
    const uint64_t t_sync = sync_ps(env, tk);
    if (t_scl <= t_sync)
    {
        return -2;
    }
    const uint64_t budget = t_scl - t_sync;             /* (L+1 + H+1) * tp  */

    for (uint32_t presc = 0U; presc <= 15U; presc++)
    {
        const uint64_t tp    = (uint64_t)(presc + 1U) * tk;
        const uint64_t total = div_round(budget, tp);   /* L+1 + H+1 ticks   */
        if (total < 2U)
        {
            continue;
        }
        uint64_t low = div_round(total * low_frac_x1000, 1000U);
        const uint64_t low_min = div_ceil(tlow_min, tp);
        if (low < low_min) { low = low_min; }
        if (low >= total)  { continue; }
        const uint64_t high = total - low;
        if ((high * tp) < thigh_min)                    { continue; }
        if ((low > 256U) || (high > 256U))              { continue; }

        /* SCLDEL: setup after SDA settles; must cover rise + tSU;DAT       */
        uint64_t scldel_t = div_ceil((uint64_t)env->rise_ns * PS_PER_NS + tsu_min, tp);
        uint64_t scldel   = (scldel_t > 0U) ? (scldel_t - 1U) : 0U;
        /* SDADEL: hold after SCL falls, minus the fixed detection delay    */
        const uint64_t fixed = (uint64_t)env->taf_ns * PS_PER_NS + 3U * tk;
        const uint64_t hold  = (uint64_t)env->fall_ns * PS_PER_NS + thd_target;
        uint64_t sdadel = (hold > fixed) ? div_ceil(hold - fixed, tp) : 0U;
        if ((scldel > 15U) || (sdadel > 15U))           { continue; }
        /* hold delay + setup delay must both fit inside the low period     */
        if ((sdadel * tp + fixed + (scldel + 1U) * tp) > (low * tp))
        {
            continue;
        }

        out->presc  = (uint8_t)presc;
        out->scll   = (uint8_t)(low - 1U);
        out->sclh   = (uint8_t)(high - 1U);
        out->sdadel = (uint8_t)sdadel;
        out->scldel = (uint8_t)scldel;
        out->timingr = ((uint32_t)presc << 28) | ((uint32_t)scldel << 20) |
                       ((uint32_t)sdadel << 16) | ((uint32_t)(high - 1U) << 8) |
                       (uint32_t)(low - 1U);
        out->tlow_ns  = (uint32_t)((low * tp) / PS_PER_NS);
        out->thigh_ns = (uint32_t)((high * tp) / PS_PER_NS);
        out->predicted_hz = dut_timing_predict_hz(env, out->timingr);
        return 0;
    }
    return -2;
}
