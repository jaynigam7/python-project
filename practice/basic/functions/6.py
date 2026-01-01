def print_sum(n):
    add=0
    i=0
    while(i<=n):
       add+=i
       i+=1
    print(add)

a=int(input("Enter the number(greater than zero):"))
print_sum(a)
