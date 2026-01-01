def Smallest(n,m,o):
    if(n<m & n<o):
        print(f"{n} is the smallest number")
    elif(m<n & m<o):
        print(f"{m} is the smallest number")
    else:
        print(f"{o} is the smallest number")
    
a=int(input("Enter the number-1:"))
b=int(input("Enter the number-2:"))
c=int(input("Enter the number-3:"))
Smallest(a,b,c)