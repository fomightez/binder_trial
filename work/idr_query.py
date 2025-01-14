# !/usr/bin/env python
# coding: utf-8

# Basic imports and setup

# In[535]:
from sqlglot.executor import execute
from sqlglot import exp, parse_one
import subprocess
import json
import os
import tempfile
import sys

def idr_query(SQL, return_data=True):

    # handles a conjuction of simple constraint clauses only TODO Generalise this code.
    table_name = ''
    where_clause = ''
    column_name = ''
    found_where = False
    found_constraints = False
    found_EQ = False
    found_Not = False
    found_Negated_Boolean = False
    too_complex = False
    eq_constraints = {}

    for node_tuple in parse_one(SQL).walk(bfs=False):
        # print(type(node_tuple[0]), node_tuple[0].name)
        if isinstance(node_tuple[0], exp.Identifier):
            # for current purposes the Identifiers may be ignored.
            # print('ignoring', str(node_tuple[0]))
            continue
        if isinstance(node_tuple[0], exp.Group) or isinstance(node_tuple[0], exp.Having) or isinstance(node_tuple[0],
                                                                                                       exp.Order):
            found_where = False
            found_constraints = False
            continue
        if isinstance(node_tuple[0], exp.Table):
            table_name = str(node_tuple[0])
            continue
        if isinstance(node_tuple[0], exp.Where):
            where_clause = str(node_tuple[0])
            found_where = True
            continue
        if found_where:
            if isinstance(node_tuple[0], exp.And):
                continue
            elif isinstance(node_tuple[0], exp.EQ) or isinstance(node_tuple[0], exp.Not) or isinstance(node_tuple[0],
                                                                                                       exp.Column):
                found_where = False
                found_constraints = True
            else:
                too_complex = True
                continue
        if found_constraints and not found_EQ and not found_Not:
            if isinstance(node_tuple[0], exp.EQ):
                found_EQ = True
                continue
            if isinstance(node_tuple[0], exp.Not):
                found_Not = True
                continue
            if isinstance(node_tuple[0], exp.Column):
                eq_constraints[str(node_tuple[0])] = True
                continue
            too_complex = True
            continue
        if found_constraints and found_EQ and column_name == '':
            if isinstance(node_tuple[0], exp.Column):
                column_name = str(node_tuple[0])
                continue
            too_complex = True
            continue
        if found_constraints and found_EQ and column_name != '':
            if isinstance(node_tuple[0], exp.Literal):
                # print(node_tuple[0].is_string, str(node_tuple[0]))

                eq_constraints[column_name] = str(node_tuple[0]) if node_tuple[0].is_string else float(
                    str(node_tuple[0]))
                found_EQ = False
                column_name = ''
                continue
            too_complex = True
            continue
        if found_constraints and found_Not:
            if isinstance(node_tuple[0], exp.Column):
                eq_constraints[str(node_tuple[0])] = False
                found_Not = False
                continue
            too_complex = True
            continue

    # print('table', table_name)
    # print(where_clause)
    # print(eq_constraints)
    # print(too_complex)

    # In[538]:

    with open('work/'+table_name.lower() + '.mzn', 'r') as file:
        model = file.read()
    # print(model)

    # Merge in the constraints in the query to get the model to be fed to MiniZinc

    model += "\n" + where_clause.replace("WHERE", "constraint").replace("AND", "/\\").replace("OR", "\\/") + ";"
    model_fn = tempfile.NamedTemporaryFile().name
    mf = open(model_fn + ".mzn", 'w')
    mf.write(model)
    mf.close()

    # print (model)

    # Run MiniZinc model and save result

    # In[541]:

    path_to_minizinc = "C:/Program Files/MiniZinc/minizinc" if sys.platform.startswith('win32') else "/usr/bin/minizinc"
    path_to_optimathsat = "C:/Program Files/MiniZinc/bin/optimathsat" if sys.platform.startswith('win32') else "/usr/bin/optimathsat"

    result = subprocess.run([path_to_minizinc, "--compile", model_fn + ".mzn"])

    # In[542]:

    # result = subprocess.run(["C:\Program Files\MiniZinc\minizinc.exe", "-c", model_fn], stdout=subprocess.PIPE)
    # print(result.stdout.decode('utf-8'))

    result = subprocess.run(
        [ path_to_optimathsat , "-input=fzn", "-opt.fzn.max_solutions=1000",
         "-opt.fzn.finite_precision=12", "-opt.fzn.finite_precision_model=true",
         "-opt.fzn.all_solutions=true", "-opt.fzn.output_var_file=-", "-model_generation=true",
         model_fn + ".fzn"],
        stdout=subprocess.PIPE)  # "-opt.fzn.output_var_file="+model_fn+"_vars.txt",
    output = result.stdout.decode('utf-8')
    # print(output)

    # In[543]:

    data_output = []
    data = False
    column = []
    for line in output.splitlines():
        if not data:
            if line == "% allsat model":
                data = True
        if data:
            if line == "% allsat model":
                column = []
            elif line == "----------":

                data_output.append('{' + ', '.join(column) + '}')
            elif line == "==========":
                pass
            else:
                x = line.replace(";", "").split("=")
                column.append('"' + x[0].strip() + '": ' + x[1].strip())
    solver_data = json.loads('[' + ', '.join(data_output) + ']')
    # print(solver_data)

    # In[544]:

    # clean up TODO Complete the cleanup
    os.remove(model_fn + ".mzn")
    os.remove(model_fn + ".ozn")
    os.remove(model_fn + ".fzn")

    # Put output into a list of dict as data ready to run

    # In[545]:

    table_input = {table_name.lower(): [x | eq_constraints for x in solver_data]}  # | eq_constraints
    # print(eq_constraints)
    # print(table_input)

    # Run the query

    # In[546]:

    # print (SQL)
    res = execute(
        SQL,
        tables=table_input
    )

    # In[547]:

    # short_input = {'act_conveyance_duty': table_input['act_conveyance_duty'][:4]}
    # SQLtest = """select
    #     product_name,
    #     min(price) min_price
    # from products
    # group by product_name
    #     ;"""
    # res = execute(
    #     """select product_name, imported,  min(price) min_price from products group by product_name, imported;""",
    #     tables={'products':[{'product_name': 'Bike', 'price': 100, 'imported': True},{'product_name': 'Tent', 'price': 200, 'imported': True},{'product_name': 'Bike', 'price': 300,  'imported': False}]}
    # )
    if return_data:
        return (res.columns, res.rows)
    else:
        return '|' + '|'.join(res.columns) + '|' + "\n" + '|' + '|'.join(
            ["----" for x in res.columns]) + '|' + "\n" + "\n".join(
            ['|' + '|'.join([str(val) for val in r]) + '|' for r in res.rows])

    # print(res.columns)
    # print()

    # print(table_mkdn)
    # print(res.columns)
    # for i in res.rows:
    #     print(i)
    #     for j in i:
    #         print (j)

    # Present the output.
