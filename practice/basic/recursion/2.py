def counting(n):
    if(n==0):
        return
    else:
      counting(n-1)
    print(n)
    
a=int(input("Enter the number:"))
counting(a)
