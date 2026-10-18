/* Contract every kernel translation unit implements. Kept separate from the
 * benchmark driver so a kernel can be compiled and inspected on its own. */
#ifndef KERNEL_H
#define KERNEL_H

typedef struct {
    const char *name;        /* matches the source file name                  */
    double flops_per_elem;   /* analytic FLOPs per element                    */
    double bytes_per_elem;   /* unique bytes touched per element              */
    const char *property;    /* the vectoriser property under test            */
} kernel_meta_t;

extern const kernel_meta_t KERNEL_META;
void   kernel_setup(long n);
double kernel_run(long n);
void   kernel_teardown(void);

#endif
