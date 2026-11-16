# Operación simulada de enero a agosto de 2017

Datos reales de Kaggle. Corte histórico 2016-12-31; bandeja del 2017-01-01 al 2017-08-15 (227 días,
33 cortes semanales). Ejecutado con `python -m motor_reposicion.cli operar --hasta 2017-08-15`, que hace
los mismos pasos que los DAGs (en Airflow los pronósticos salen idénticos, ver `airflow.md`). Duración: 710 s en una máquina de 2 núcleos.

## Resumen del seguimiento (pronósticos publicados contra ventas reales)

| Indicador | Motor | Baseline |
|---|---|---|
| Costo total del pedido sugerido (merma + quiebre) | 11 501 452 | 13 560 688 |
| WAPE de la venta esperada | 0.147 | 0.168 |
| Semanas con menor costo | 28 de 32 | 4 de 32 |

Ahorro frente al baseline: **15.2 %**. Se evaluaron 32 pronósticos y 501 días-pronóstico
(el de 2017-08-14 no tiene días reales que comparar).

## WAPE promedio por día del horizonte

| Día | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Motor | 0.141 | 0.133 | 0.136 | 0.157 | 0.140 | 0.180 | 0.146 | 0.139 | 0.133 | 0.136 | 0.158 | 0.140 | 0.183 | 0.145 | 0.139 | 0.133 |
| Baseline | 0.175 | 0.162 | 0.175 | 0.170 | 0.159 | 0.166 | 0.179 | 0.170 | 0.161 | 0.174 | 0.170 | 0.159 | 0.168 | 0.180 | 0.170 | 0.160 |

El motor es mejor en 14 de los 16 días; los días 6 y 13 (domingos) el baseline tiene menor error.

## Por pronóstico (corte)

| Corte | Decisión | Modelo vigente | WAPE | Costo motor | Costo baseline | Ahorro |
|---|---|---|---|---|---|---|
| 2017-01-02 | promover_candidato | boosting_2017-01-02 | 0.141 | 371 244 | 683 141 | 45.7 % |
| 2017-01-09 | conservar_vigente | boosting_2017-01-02 | 0.151 | 369 173 | 798 197 | 53.8 % |
| 2017-01-16 | conservar_vigente | boosting_2017-01-02 | 0.160 | 392 310 | 687 302 | 42.9 % |
| 2017-01-23 | conservar_vigente | boosting_2017-01-02 | 0.147 | 376 971 | 435 488 | 13.4 % |
| 2017-01-30 | conservar_vigente | boosting_2017-01-02 | 0.141 | 348 750 | 369 812 | 5.7 % |
| 2017-02-06 | conservar_vigente | boosting_2017-01-02 | 0.135 | 303 542 | 335 281 | 9.5 % |
| 2017-02-13 | conservar_vigente | boosting_2017-01-02 | 0.171 | 386 740 | 427 169 | 9.5 % |
| 2017-02-20 | conservar_vigente | boosting_2017-01-02 | 0.164 | 401 127 | 498 953 | 19.6 % |
| 2017-02-27 | conservar_vigente | boosting_2017-01-02 | 0.137 | 368 484 | 472 830 | 22.1 % |
| 2017-03-06 | conservar_vigente | boosting_2017-01-02 | 0.130 | 340 798 | 336 616 | -1.2 % |
| 2017-03-13 | promover_candidato | boosting_2017-03-13 | 0.137 | 338 742 | 308 283 | -9.9 % |
| 2017-03-20 | conservar_vigente | boosting_2017-03-13 | 0.154 | 362 641 | 423 527 | 14.4 % |
| 2017-03-27 | conservar_vigente | boosting_2017-03-13 | 0.155 | 386 504 | 438 023 | 11.8 % |
| 2017-04-03 | conservar_vigente | boosting_2017-03-13 | 0.153 | 381 117 | 335 588 | -13.6 % |
| 2017-04-10 | conservar_vigente | boosting_2017-03-13 | 0.161 | 410 009 | 400 835 | -2.3 % |
| 2017-04-17 | conservar_vigente | boosting_2017-03-13 | 0.162 | 451 951 | 539 567 | 16.2 % |
| 2017-04-24 | conservar_vigente | boosting_2017-03-13 | 0.166 | 476 529 | 560 418 | 15.0 % |
| 2017-05-01 | conservar_vigente | boosting_2017-03-13 | 0.168 | 441 532 | 463 218 | 4.7 % |
| 2017-05-08 | conservar_vigente | boosting_2017-03-13 | 0.164 | 408 326 | 419 379 | 2.6 % |
| 2017-05-15 | conservar_vigente | boosting_2017-03-13 | 0.148 | 384 477 | 414 754 | 7.3 % |
| 2017-05-22 | promover_candidato | boosting_2017-05-22 | 0.147 | 385 116 | 465 966 | 17.4 % |
| 2017-05-29 | promover_candidato | boosting_2017-05-29 | 0.151 | 388 053 | 428 610 | 9.5 % |
| 2017-06-05 | conservar_vigente | boosting_2017-05-29 | 0.146 | 320 568 | 325 818 | 1.6 % |
| 2017-06-12 | conservar_vigente | boosting_2017-05-29 | 0.134 | 279 431 | 328 820 | 15.0 % |
| 2017-06-19 | conservar_vigente | boosting_2017-05-29 | 0.129 | 312 240 | 330 059 | 5.4 % |
| 2017-06-26 | promover_candidato | boosting_2017-06-26 | 0.125 | 330 060 | 331 354 | 0.4 % |
| 2017-07-03 | conservar_vigente | boosting_2017-06-26 | 0.119 | 290 726 | 295 382 | 1.6 % |
| 2017-07-10 | conservar_vigente | boosting_2017-06-26 | 0.121 | 291 154 | 308 871 | 5.7 % |
| 2017-07-17 | conservar_vigente | boosting_2017-06-26 | 0.132 | 339 892 | 400 959 | 15.2 % |
| 2017-07-24 | promover_candidato | boosting_2017-07-24 | 0.137 | 348 277 | 404 925 | 14.0 % |
| 2017-07-31 | conservar_vigente | boosting_2017-07-24 | 0.163 | 340 620 | 406 135 | 16.1 % |
| 2017-08-07 | conservar_vigente | boosting_2017-07-24 | 0.192 | 174 345 | 185 406 | 6.0 % |
| 2017-08-14 | conservar_vigente | boosting_2017-07-24 | – | – | – | – |

## Decisiones de la compuerta

6 promociones y 27 semanas conservando el vigente. Métricas en la validación (costo total):

| Corte | Candidato | Baseline | Vigente | Decisión | Motivo |
|---|---|---|---|---|---|
| 2017-01-02 | 985 553 | 1 329 125 | – | promover_candidato | No hay modelo vigente y el candidato (985 552.73) mejora al baseline (1 329 124.74) |
| 2017-01-09 | 937 735 | 1 318 479 | 943 807 | conservar_vigente | Mejora frente al vigente de 0.64 %, menor que 2.00 % (937 734.99 vs 943 806.87) |
| 2017-01-16 | 875 552 | 1 353 160 | 874 563 | conservar_vigente | Mejora frente al vigente de -0.11 %, menor que 2.00 % (875 552.05 vs 874 562.65) |
| 2017-01-23 | 785 287 | 1 024 074 | 751 626 | conservar_vigente | Mejora frente al vigente de -4.48 %, menor que 2.00 % (785 286.92 vs 751 626.38) |
| 2017-01-30 | 658 669 | 728 302 | 609 333 | conservar_vigente | Mejora frente al vigente de -8.10 %, menor que 2.00 % (658 669.49 vs 609 332.90) |
| 2017-02-06 | 695 459 | 621 554 | 601 076 | conservar_vigente | El candidato (695 459.42) no mejora al baseline (621 554.05) en costo_total; se conserva el vigente |
| 2017-02-13 | 700 626 | 633 307 | 591 652 | conservar_vigente | El candidato (700 626.50) no mejora al baseline (633 307.18) en costo_total; se conserva el vigente |
| 2017-02-20 | 566 934 | 601 900 | 535 124 | conservar_vigente | Mejora frente al vigente de -5.94 %, menor que 2.00 % (566 933.72 vs 535 124.24) |
| 2017-02-27 | 602 860 | 624 021 | 567 534 | conservar_vigente | Mejora frente al vigente de -6.22 %, menor que 2.00 % (602 860.28 vs 567 534.27) |
| 2017-03-06 | 583 695 | 722 597 | 592 002 | conservar_vigente | Mejora frente al vigente de 1.40 %, menor que 2.00 % (583 694.92 vs 592 002.15) |
| 2017-03-13 | 593 873 | 730 092 | 611 301 | promover_candidato | El candidato baja costo_total 2.85 % frente al vigente (593 873.04 vs 611 301.12) |
| 2017-03-20 | 639 872 | 698 978 | 608 940 | conservar_vigente | Mejora frente al vigente de -5.08 %, menor que 2.00 % (639 872.45 vs 608 939.62) |
| 2017-03-27 | 604 746 | 605 406 | 552 051 | conservar_vigente | Mejora frente al vigente de -9.55 %, menor que 2.00 % (604 745.64 vs 552 050.87) |
| 2017-04-03 | 613 536 | 640 412 | 563 370 | conservar_vigente | Mejora frente al vigente de -8.90 %, menor que 2.00 % (613 536.40 vs 563 369.94) |
| 2017-04-10 | 631 885 | 619 567 | 586 090 | conservar_vigente | El candidato (631 885.31) no mejora al baseline (619 567.45) en costo_total; se conserva el vigente |
| 2017-04-17 | 672 583 | 666 284 | 637 892 | conservar_vigente | El candidato (672 583.10) no mejora al baseline (666 284.23) en costo_total; se conserva el vigente |
| 2017-04-24 | 685 729 | 714 921 | 660 451 | conservar_vigente | Mejora frente al vigente de -3.83 %, menor que 2.00 % (685 729.49 vs 660 450.80) |
| 2017-05-01 | 710 529 | 749 572 | 696 521 | conservar_vigente | Mejora frente al vigente de -2.01 %, menor que 2.00 % (710 529.00 vs 696 520.88) |
| 2017-05-08 | 765 607 | 823 278 | 767 881 | conservar_vigente | Mejora frente al vigente de 0.30 %, menor que 2.00 % (765 607.43 vs 767 881.34) |
| 2017-05-15 | 777 817 | 857 774 | 774 545 | conservar_vigente | Mejora frente al vigente de -0.42 %, menor que 2.00 % (777 817.36 vs 774 544.62) |
| 2017-05-22 | 710 221 | 876 691 | 785 110 | promover_candidato | El candidato baja costo_total 9.54 % frente al vigente (710 221.14 vs 785 110.45) |
| 2017-05-29 | 649 794 | 761 278 | 665 893 | promover_candidato | El candidato baja costo_total 2.42 % frente al vigente (649 793.72 vs 665 893.46) |
| 2017-06-05 | 674 736 | 787 263 | 662 997 | conservar_vigente | Mejora frente al vigente de -1.77 %, menor que 2.00 % (674 735.99 vs 662 997.18) |
| 2017-06-12 | 635 648 | 727 379 | 637 227 | conservar_vigente | Mejora frente al vigente de 0.25 %, menor que 2.00 % (635 648.14 vs 637 227.03) |
| 2017-06-19 | 592 568 | 689 690 | 602 530 | conservar_vigente | Mejora frente al vigente de 1.65 %, menor que 2.00 % (592 567.87 vs 602 529.56) |
| 2017-06-26 | 544 481 | 628 681 | 564 531 | promover_candidato | El candidato baja costo_total 3.55 % frente al vigente (544 481.12 vs 564 531.35) |
| 2017-07-03 | 543 411 | 574 212 | 539 264 | conservar_vigente | Mejora frente al vigente de -0.77 %, menor que 2.00 % (543 411.11 vs 539 264.30) |
| 2017-07-10 | 515 430 | 555 705 | 515 918 | conservar_vigente | Mejora frente al vigente de 0.09 %, menor que 2.00 % (515 430.26 vs 515 918.03) |
| 2017-07-17 | 500 232 | 540 154 | 505 197 | conservar_vigente | Mejora frente al vigente de 0.98 %, menor que 2.00 % (500 231.94 vs 505 197.31) |
| 2017-07-24 | 504 007 | 553 771 | 515 576 | promover_candidato | El candidato baja costo_total 2.24 % frente al vigente (504 006.80 vs 515 575.84) |
| 2017-07-31 | 519 395 | 538 744 | 523 233 | conservar_vigente | Mejora frente al vigente de 0.73 %, menor que 2.00 % (519 394.70 vs 523 233.24) |
| 2017-08-07 | 559 642 | 629 577 | 553 924 | conservar_vigente | Mejora frente al vigente de -1.03 %, menor que 2.00 % (559 642.36 vs 553 924.22) |
| 2017-08-14 | 600 233 | 687 993 | 601 647 | conservar_vigente | Mejora frente al vigente de 0.24 %, menor que 2.00 % (600 232.70 vs 601 646.79) |
