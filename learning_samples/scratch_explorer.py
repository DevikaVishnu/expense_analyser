import pdfplumber

with pdfplumber.open("../expense_reports/IslandFederal_checking/bank_statement/2026_6_june.pdf") as pdf:
    first_page = pdf.pages[0]
    second_page = pdf.pages[1]
    third_page = pdf.pages[2]
    print(first_page.chars[0])

    print()
    print(first_page.extract_text())
    print()
    #print(second_page.extract_text())
    print()
    print(third_page.extract_text())

