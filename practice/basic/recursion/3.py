def add(n):
    sum=0
    if(n==0):
        return
    else:
     sum += add(n-1)

a=int(input("Enter the number:"))
add(a)
import numpy as np
np.add(23) 