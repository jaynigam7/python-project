import PyPDF2
import pikepdf
import os

def add_password_batch(pdf_list, output_folder, password):
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    for pdf in pdf_list:
        try:
            pdf_reader = PyPDF2.PdfReader(pdf)
            pdf_writer = PyPDF2.PdfWriter()

            for page in pdf_reader.pages:
                pdf_writer.add_page(page)

            pdf_writer.encrypt(password)

            file_name = os.path.basename(pdf)
            output_pdf = os.path.join(output_folder, f"protected_{file_name}")

            with open(output_pdf, "wb") as f:
                pdf_writer.write(f)

            print(f" Protected: {file_name}")

        except Exception as e:
            print(f" Failed: {pdf} | Error: {e}")


def remove_password_batch(pdf_list, output_folder, password):
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    for pdf in pdf_list:
        try:
            file_name = os.path.basename(pdf)
            output_pdf = os.path.join(output_folder, f"unlocked_{file_name}")

            with pikepdf.open(pdf, password=password) as pdf_obj:
                pdf_obj.save(output_pdf)

            print(f" Unlocked: {file_name}")

        except Exception as e:
            print(f" Failed: {pdf} | Error: {e}")


def get_pdf_list():
    print("\nEnter all PDF paths (one per line).")
    print("Type 'done' when finished:\n")

    pdfs = []
    while True:
        path = input("> ")
        if path.lower() == "done":
            break
        if os.path.exists(path):
            pdfs.append(path)
        else:
            print(" Invalid path! Try again.")

    return pdfs


def menu():
    print("\n===== Batch PDF Protection Manager =====")
    print("1. Add Password to Multiple PDFs")
    print("2. Remove Password from Multiple PDFs")
    print("3. Exit")

    choice = input("Enter choice: ")

    if choice == "1":
        pdfs = get_pdf_list()
        output = input("Enter output folder: ")
        pwd = input("Enter password to set: ")
        add_password_batch(pdfs, output, pwd)

    elif choice == "2":
        pdfs = get_pdf_list()
        output = input("Enter output folder: ")
        pwd = input("Enter password to unlock: ")
        remove_password_batch(pdfs, output, pwd)

    elif choice == "3":
        print("Exiting...")
        exit()

    else:
        print(" Invalid Choice!")


while True:
    menu()
