/**
 * [v0.1]
 * @file    dut_proto.c
 * @brief   Loopback-DUT line protocol (see dut_proto.h, PROTOCOL.md §2-3).
 *          No libc beyond <stddef.h>/<stdint.h> types: keeps the host test
 *          and the target identical.
 */
#include "dut_proto.h"
#include "dut_regmap.h"

#define MAX_TOK  (LB_MAX_XFER + 12U)

/* ------------------------------------------------------------------ util */
static char up(char c) { return (c >= 'a' && c <= 'z') ? (char)(c - 32) : c; }

static int streq_ci(const char *a, const char *b)
{
    while (*a && *b)
    {
        if (up(*a) != up(*b)) { return 0; }
        a++; b++;
    }
    return (*a == '\0') && (*b == '\0');
}

static int hexval(char c)
{
    c = up(c);
    if (c >= '0' && c <= '9') { return c - '0'; }
    if (c >= 'A' && c <= 'F') { return c - 'A' + 10; }
    return -1;
}

/* hex 1..2 digits (optional 0x) -> byte */
static int parse_hex_u8(const char *s, uint8_t *out)
{
    if ((s[0] == '0') && ((s[1] == 'x') || (s[1] == 'X'))) { s += 2; }
    uint32_t v = 0U, n = 0U;
    for (; *s; s++, n++)
    {
        const int h = hexval(*s);
        if ((h < 0) || (n >= 2U)) { return 0; }
        v = (v << 4) | (uint32_t)h;
    }
    if (n == 0U) { return 0; }
    *out = (uint8_t)v;
    return 1;
}

static int parse_dec_u32(const char *s, uint32_t *out)
{
    uint64_t v = 0U;
    if (*s == '\0') { return 0; }
    for (; *s; s++)
    {
        if ((*s < '0') || (*s > '9')) { return 0; }
        v = v * 10U + (uint64_t)(*s - '0');
        if (v > 0xFFFFFFFFULL) { return 0; }
    }
    *out = (uint32_t)v;
    return 1;
}

uint8_t dut_line_crc(const char *s, size_t n)
{
    uint8_t crc = 0U;
    for (size_t i = 0U; i < n; i++)
    {
        crc = dut_crc8_update(crc, (uint8_t)s[i]);
    }
    return crc;
}

size_t dut_line_seal(char *buf, size_t len, size_t cap)
{
    static const char hx[] = "0123456789ABCDEF";
    if ((len + 5U) > cap) { return 0U; }
    const uint8_t c = dut_line_crc(buf, len);
    buf[len + 0U] = ' ';
    buf[len + 1U] = '*';
    buf[len + 2U] = hx[c >> 4];
    buf[len + 3U] = hx[c & 0xFU];
    buf[len + 4U] = '\n';
    return len + 5U;
}

const char *dut_op_name(dut_op_t op)
{
    switch (op)
    {
        case DUT_OP_W:   return "W";
        case DUT_OP_R:   return "R";
        case DUT_OP_WR:  return "WR";
        case DUT_OP_WPR: return "WPR";
        default:         return "?";
    }
}

/* ------------------------------------------------------------- parsing */
static dut_err_t parse_resp(const char *s, uint8_t *resp)
{
    uint32_t v;
    if (!parse_dec_u32(s, &v) || (v < 1U) || (v > 2U)) { return DUT_E_ARG; }
    *resp = (uint8_t)v;
    return DUT_OK;
}

static dut_err_t parse_set(char **t, int n, dut_cmd_t *c)
{
    if (n < 3) { return DUT_E_SYNTAX; }
    if (streq_ci(t[1], "SPEED"))
    {
        if ((n != 3) && (n != 5)) { return DUT_E_SYNTAX; }
        c->type = DUT_CMD_SET_SPEED;
        if (!parse_dec_u32(t[2], &c->v1)) { return DUT_E_ARG; }
        c->v2 = LB_RISE_NS;
        c->v3 = LB_FALL_NS;
        if (n == 5)
        {
            if (!parse_dec_u32(t[3], &c->v2) || !parse_dec_u32(t[4], &c->v3))
            {
                return DUT_E_ARG;
            }
        }
        return DUT_OK;
    }
    if (n != 4 && !(streq_ci(t[1], "STRETCH") && n == 5)) { return DUT_E_SYNTAX; }
    if (parse_resp(t[2], &c->resp) != DUT_OK) { return DUT_E_ARG; }
    if (streq_ci(t[1], "ADDR"))
    {
        uint8_t a;
        if ((n != 4) || !parse_hex_u8(t[3], &a) || (a > 0x7FU)) { return DUT_E_ARG; }
        c->type = DUT_CMD_SET_ADDR;
        c->v1 = a;
        return DUT_OK;
    }
    if (streq_ci(t[1], "EN"))
    {
        if ((n != 4) || !parse_dec_u32(t[3], &c->v1) || (c->v1 > 1U)) { return DUT_E_ARG; }
        c->type = DUT_CMD_SET_EN;
        return DUT_OK;
    }
    if (streq_ci(t[1], "PEC"))
    {
        if ((n != 4) || !parse_dec_u32(t[3], &c->v1) || (c->v1 > LB_MAX_XFER)) { return DUT_E_ARG; }
        c->type = DUT_CMD_SET_PEC;
        return DUT_OK;
    }
    if (streq_ci(t[1], "STRETCH"))
    {
        if ((n != 5) || !parse_dec_u32(t[3], &c->v1) || !parse_dec_u32(t[4], &c->v2) ||
            (c->v1 > LB_MAX_XFER) || (c->v2 > LB_MAX_STRETCH_US))
        {
            return DUT_E_ARG;
        }
        c->type = DUT_CMD_SET_STRETCH;
        return DUT_OK;
    }
    return DUT_E_SYNTAX;
}

static dut_err_t parse_run(char **t, int n, dut_cmd_t *c)
{
    /* strip trailing key=value options */
    c->rep = 1U;
    c->gap_us = 0U;
    while (n > 0)
    {
        char *eq = 0;
        for (char *p = t[n - 1]; *p; p++) { if (*p == '=') { eq = p; break; } }
        if (eq == 0) { break; }
        *eq = '\0';
        uint32_t v;
        if (!parse_dec_u32(eq + 1, &v)) { return DUT_E_ARG; }
        if (streq_ci(t[n - 1], "REP"))
        {
            if ((v < 1U) || (v > LB_MAX_REPEAT)) { return DUT_E_ARG; }
            c->rep = (uint16_t)v;
        }
        else if (streq_ci(t[n - 1], "GAP"))
        {
            c->gap_us = v;
        }
        else
        {
            return DUT_E_SYNTAX;
        }
        n--;
    }

    if (n < 4) { return DUT_E_SYNTAX; }
    if (!parse_dec_u32(t[1], &c->seq)) { return DUT_E_ARG; }
    if (!parse_hex_u8(t[3], &c->addr) || (c->addr > 0x7FU)) { return DUT_E_ARG; }

    int first_data;
    if (streq_ci(t[2], "W"))        { c->op = DUT_OP_W;   first_data = 4; }
    else if (streq_ci(t[2], "R"))   { c->op = DUT_OP_R;   first_data = -1; }
    else if (streq_ci(t[2], "WR"))  { c->op = DUT_OP_WR;  first_data = 5; }
    else if (streq_ci(t[2], "WPR")) { c->op = DUT_OP_WPR; first_data = 5; }
    else { return DUT_E_SYNTAX; }

    c->rlen = 0U;
    c->wlen = 0U;
    if (c->op != DUT_OP_W)
    {
        uint32_t r;
        if (!parse_dec_u32(t[4], &r) || (r < 1U) || (r > LB_MAX_XFER)) { return DUT_E_ARG; }
        c->rlen = (uint16_t)r;
    }
    if (first_data < 0)
    {
        return (n == 5) ? DUT_OK : DUT_E_SYNTAX;
    }
    if (n <= first_data) { return DUT_E_SYNTAX; }       /* >= 1 write byte  */
    if ((uint32_t)(n - first_data) > LB_MAX_XFER) { return DUT_E_LONG; }
    for (int i = first_data; i < n; i++)
    {
        if (!parse_hex_u8(t[i], &c->wdata[c->wlen])) { return DUT_E_ARG; }
        c->wlen++;
    }
    return DUT_OK;
}

dut_err_t dut_parse_line(char *line, dut_cmd_t *c)
{
    char *t[MAX_TOK];
    int n = 0;
    size_t len = 0U;

    c->type = DUT_CMD_NONE;
    while (line[len] != '\0') { len++; }
    while ((len > 0U) && ((line[len - 1U] == '\r') || (line[len - 1U] == '\n') ||
                          (line[len - 1U] == ' ')))
    {
        line[--len] = '\0';
    }
    if (len > LB_LINE_MAX) { return DUT_E_LONG; }

    /* optional " *CC" checksum */
    if ((len >= 4U) && (line[len - 4U] == ' ') && (line[len - 3U] == '*'))
    {
        const int h = hexval(line[len - 2U]), l = hexval(line[len - 1U]);
        if ((h < 0) || (l < 0)) { return DUT_E_CRC; }
        if (dut_line_crc(line, len - 4U) != (uint8_t)((h << 4) | l)) { return DUT_E_CRC; }
        line[len - 4U] = '\0';
    }

    for (char *p = line; *p; )
    {
        while (*p == ' ' || *p == '\t') { *p++ = '\0'; }
        if (*p == '\0') { break; }
        if (n >= (int)MAX_TOK) { return DUT_E_LONG; }
        t[n++] = p;
        while (*p && *p != ' ' && *p != '\t') { p++; }
    }
    if (n == 0) { return DUT_OK; }                      /* blank line       */

    if (streq_ci(t[0], "PING"))   { c->type = DUT_CMD_PING;   return (n == 1) ? DUT_OK : DUT_E_SYNTAX; }
    if (streq_ci(t[0], "STATUS")) { c->type = DUT_CMD_STATUS; return (n == 1) ? DUT_OK : DUT_E_SYNTAX; }
    if (streq_ci(t[0], "RESET"))  { c->type = DUT_CMD_RESET;  return (n == 1) ? DUT_OK : DUT_E_SYNTAX; }
    if (streq_ci(t[0], "SET"))    { return parse_set(t, n, c); }
    if (streq_ci(t[0], "RUN"))
    {
        const dut_err_t e = parse_run(t, n, c);
        if (e == DUT_OK) { c->type = DUT_CMD_RUN; }
        return e;
    }
    return DUT_E_SYNTAX;
}
