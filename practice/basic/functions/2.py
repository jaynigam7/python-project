def max(n,m):
     if(n>m):
          print(f"{n} is greater than {m}")
     elif(m==n):
          print(f"Both {m} and {n} are equal")
     else:
          print(f"{m} is greater than {n}")

a=int(input("Enter the number:"))
b=int(input("Enter the number:"))
max(a,b)
