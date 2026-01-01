def num(n):
    if(n==1):
        return 1
    else:
        print(n)
        return num(n-1)
    
a=int(input("Enter the number:"))
print(num(a))