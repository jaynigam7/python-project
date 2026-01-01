def counting(n):
    count=0
    b={"a","e","i","o","u","A","E","I","O","U"}
    i=0
    for ch in n:
        if ch in b:
         count+=1
    print(count)

a=input("Enter the sentence:")
counting(a)