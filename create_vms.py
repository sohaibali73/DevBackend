import base64, os  
base = r'C:\Users\SohaibAli\Documents\PotomacDeveloper\ViewModels'  
files = {}  
files['ResearcherViewModel.cs'] = base64.b64decode(open('r_b64.txt').read()) 
