# AUTOGENERATED! DO NOT EDIT! File to edit: ../01_funccall.ipynb.

# %% auto 0
__all__ = ['empty', 'custom_types', 'get_schema', 'PathArg', 'python', 'mk_ns', 'call_func', 'call_func_async']

# %% ../01_funccall.ipynb 2
import inspect
from collections import abc
from fastcore.utils import *
from fastcore.docments import docments
from typing import get_origin, get_args, Dict, List, Optional, Tuple, Union
from types import UnionType

# %% ../01_funccall.ipynb 3
empty = inspect.Parameter.empty

# %% ../01_funccall.ipynb 11
def _types(t:type)->tuple[str,Optional[str]]:
    "Tuple of json schema type name and (if appropriate) array item name."
    if t is empty: raise TypeError('Missing type')
    tmap = {int:"integer", float:"number", str:"string", bool:"boolean", list:"array", dict:"object"}
    tmap.update({k.__name__: v for k, v in tmap.items()})
    if getattr(t, '__origin__', None) in (list,tuple):
        args = getattr(t, '__args__', None)
        item_type = "object" if not args else tmap.get(t.__args__[0].__name__, "object")
        return "array", item_type
    # if t is a string like 'int', directly use the string as the key
    elif isinstance(t, str): return tmap.get(t, "object"), None
    # if t is the type itself and a container
    elif get_origin(t): return tmap.get(get_origin(t).__name__, "object"), None
    # if t is the type itself like int, use the __name__ representation as the key
    else: return tmap.get(t.__name__, "object"), None

# %% ../01_funccall.ipynb 18
def _param(name, info):
    "json schema parameter given `name` and `info` from docments full dict."
    paramt,itemt = _types(info.anno)
    pschema = dict(type=paramt, description=info.docment or "")
    if itemt: pschema["items"] = {"type": itemt}
    if info.default is not empty: pschema["default"] = info.default
    return pschema

# %% ../01_funccall.ipynb 21
custom_types = {Path}

def _handle_type(t, defs):
    "Handle a single type, creating nested schemas if necessary"
    if t is NoneType: return {'type': 'null'}
    if t in custom_types: return {'type':'string', 'format':t.__name__}
    if isinstance(t, type) and not issubclass(t, (int, float, str, bool)) or inspect.isfunction(t):
        defs[t.__name__] = _get_nested_schema(t)
        return {'$ref': f'#/$defs/{t.__name__}'}
    return {'type': _types(t)[0]}

# %% ../01_funccall.ipynb 23
def _is_container(t):
    "Check if type is a container (list, dict, tuple, set, Union)"
    origin = get_origin(t)
    return origin in (list, dict, tuple, set, Union) if origin else False

def _is_parameterized(t):
    "Check if type has arguments (e.g. list[int] vs list, dict[str, int] vs dict)"
    return _is_container(t) and (get_args(t) != ())

# %% ../01_funccall.ipynb 29
def _handle_container(origin, args, defs):
    "Handle container types like dict, list, tuple, set, and Union"
    if origin is Union or origin is UnionType:
        return {"anyOf": [_handle_type(arg, defs) for arg in args]}
    if origin is dict:
        value_type = args[1].__args__[0] if hasattr(args[1], '__args__') else args[1]
        return {
            'type': 'object',
            'additionalProperties': (
                {'type': 'array', 'items': _handle_type(value_type, defs)}
                if hasattr(args[1], '__origin__') else _handle_type(args[1], defs)
            )
        }
    elif origin in (list, tuple, set):
        schema = {'type': 'array', 'items': _handle_type(args[0], defs)}
        if origin is set:
            schema['uniqueItems'] = True
        return schema
    return None

# %% ../01_funccall.ipynb 30
def _process_property(name, obj, props, req, defs):
    "Process a single property of the schema"
    p = _param(name, obj)
    props[name] = p
    if obj.default is empty: req[name] = True

    if _is_container(obj.anno) and _is_parameterized(obj.anno):
            p.update(_handle_container(get_origin(obj.anno), get_args(obj.anno), defs))        
    else:
        # Non-container type or container without arguments
        p.update(_handle_type(obj.anno, defs))

# %% ../01_funccall.ipynb 31
def _get_nested_schema(obj):
    "Generate nested JSON schema for a class or function"
    d = docments(obj, full=True)
    props, req, defs = {}, {}, {}

    for n, o in d.items():
        if n != 'return' and n != 'self':
            _process_property(n, o, props, req, defs)

    schema = dict(type='object', properties=props, title=obj.__name__ if isinstance(obj, type) else None)
    if req: schema['required'] = list(req)
    if defs: schema['$defs'] = defs
    return schema

# %% ../01_funccall.ipynb 35
def get_schema(f:callable, pname='input_schema')->dict:
    "Generate JSON schema for a class, function, or method"
    schema = _get_nested_schema(f)
    desc = f.__doc__
    assert desc, "Docstring missing!"
    d = docments(f, full=True)
    ret = d.pop('return')
    if ret.anno is not empty: desc += f'\n\nReturns:\n- type: {_types(ret.anno)[0]}'
    return {"name": f.__name__, "description": desc, pname: schema}

# %% ../01_funccall.ipynb 46
def PathArg(
    path: str  # A filesystem path
): return Path(path)

# %% ../01_funccall.ipynb 66
import ast, time, signal, traceback
from fastcore.utils import *

# %% ../01_funccall.ipynb 67
def _copy_loc(new, orig):
    "Copy location information from original node to new node and all children."
    new = ast.copy_location(new, orig)
    for field, o in ast.iter_fields(new):
        if isinstance(o, ast.AST): setattr(new, field, _copy_loc(o, orig))
        elif isinstance(o, list): setattr(new, field, [_copy_loc(value, orig) for value in o])
    return new

# %% ../01_funccall.ipynb 69
def _run(code:str ):
    "Run `code`, returning final expression (similar to IPython)"
    tree = ast.parse(code)
    last_node = tree.body[-1] if tree.body else None
    
    # If the last node is an expression, modify the AST to capture the result
    if isinstance(last_node, ast.Expr):
        tgt = [ast.Name(id='_result', ctx=ast.Store())]
        assign_node = ast.Assign(targets=tgt, value=last_node.value)
        tree.body[-1] = _copy_loc(assign_node, last_node)

    compiled_code = compile(tree, filename='<ast>', mode='exec')
    namespace = {}
    stdout_buffer = io.StringIO()
    saved_stdout = sys.stdout
    sys.stdout = stdout_buffer
    try: exec(compiled_code, namespace)
    finally: sys.stdout = saved_stdout
    _result = namespace.get('_result', None)
    if _result is not None: return _result
    return stdout_buffer.getvalue().strip()

# %% ../01_funccall.ipynb 74
def python(code, # Code to execute
           timeout=5 # Maximum run time in seconds before a `TimeoutError` is raised
          ): # Result of last node, if it's an expression, or `None` otherwise
    """Executes python `code` with `timeout` and returning final expression (similar to IPython).
    Raised exceptions are returned as a string, with a stack trace."""
    def handler(*args): raise TimeoutError()
    signal.signal(signal.SIGALRM, handler)
    signal.alarm(timeout)
    try: return _run(code)
    except Exception as e: return traceback.format_exc()
    finally: signal.alarm(0)

# %% ../01_funccall.ipynb 81
def mk_ns(*funcs_or_objs):
    merged = {}
    for o in funcs_or_objs:
        if isinstance(o, type): merged |= {n:getattr(o,n) for n,m in o.__dict__.items() if isinstance(m, (staticmethod, classmethod))}
        if isinstance(o, object): merged |= {n:getattr(o,n) for n, m in inspect.getmembers(o, inspect.ismethod)} | {n:m for n,m in o.__class__.__dict__.items() if isinstance(m, staticmethod)}
        if callable(o) and hasattr(o, '__name__'): merged |= {o.__name__: o}
    return merged

# %% ../01_funccall.ipynb 90
def call_func(fc_name, fc_inputs, ns):
    "Call the function `fc_name` with the given `fc_inputs` using namespace `ns`."
    if not isinstance(ns, abc.Mapping): ns = mk_ns(*ns)
    func = ns[fc_name]
    return func(**fc_inputs)

# %% ../01_funccall.ipynb 97
async def call_func_async(fc_name, fc_inputs, ns):
    "Awaits the function `fc_name` with the given `fc_inputs` using namespace `ns`."
    if not isinstance(ns, abc.Mapping): ns = mk_ns(*ns)
    func = ns[fc_name]
    return await func(**fc_inputs)
