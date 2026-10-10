/**
 * [v0.1]
 * @file    dut_app.h
 * @brief   Loopback DUT application (hardware glue). Called from the
 *          USER CODE regions of the CubeMX-generated Core/Src/main.c:
 *
 *            USER CODE BEGIN Includes :  #include "dut_app.h"
 *            USER CODE BEGIN 2        :  dut_app_init();
 *            USER CODE BEGIN 3        :  dut_app_poll();
 */
#ifndef DUT_APP_H
#define DUT_APP_H

void dut_app_init(void);
void dut_app_poll(void);

#endif /* DUT_APP_H */
