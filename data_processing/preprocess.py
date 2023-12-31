from data_formatting_utils import subtokenize_comment, subtokenize_code, compute_code_diff_spans
from data_utils import DiffExample
from method_details_extraction import extract_method_name, extract_return_type, extract_return_statements
from diff_utils import compute_minimal_comment_diffs, compute_code_diffs
import argparse
import logging
from tqdm import tqdm
import os
import re
from pygments import highlight
from pygments.lexers import JavaLexer, CppLexer, CLexer, PythonLexer, JavascriptLexer, CSharpLexer
from pygments.formatters import RawTokenFormatter
import json

logger = logging.getLogger(__name__)

def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument("--diff_filename", default="CMG-data/cmg.valid.diff", type=str,
                        help="The diff filename.")
    parser.add_argument("--msg_filename", default="CMG-data/cmg.valid.msg", type=str,
                        help="The msg filename.")
    parser.add_argument("--lang_filename", default="CMG-data/cmg.valid.lang", type=str,
                        help="The lang filename.")
    parser.add_argument("--output_dir",  type=str, default="data_processing/saved_process",
                        help="The output directory where the processed file will be written.")
    
    args = parser.parse_args()
    return args

def get_clean_code(token_vals):
    """Helper method for subtokenizing code."""
    # token_vals = [t.value for t in tokenized_code]
    new_token_vals = []
    for t in token_vals:
        n = [c for c in re.findall(r"[a-zA-Z0-9]+|[^\sa-zA-Z0-9]|[^_\sa-zA-Z0-9]", t.encode('ascii', errors='ignore').decode().strip()) if len(c) > 0]
        new_token_vals = new_token_vals + n

    token_vals = new_token_vals
    cleaned_code_tokens = []

    for c in token_vals:
        try:
            cleaned_code_tokens.append(str(c))
        except:
            pass

    return cleaned_code_tokens

def subtokenize_code(line, language='java'):
    """Subtokenizes a method, which is in string format.
       Returns list of subtokens, labels (whether each term is a subtoken of a larger token),
       and indices (index of subtoken within larger token)."""
    try:
        if language == "java":
            lexer = JavaLexer()
        elif language == "python":
            lexer = PythonLexer()
        elif language == "cpp":
            lexer = CppLexer()
        elif language == "c":
            lexer = CLexer()
        elif language == "javascript":
            lexer = JavascriptLexer()
        elif language == "csharp":
            lexer = CSharpLexer()
        else:
            print("Please modify this file. Reference: https://pygments.org/docs/lexers/")
        x = highlight(line, lexer, RawTokenFormatter())
        x = str(x, encoding='utf-8')
        tk = list()
        for y in x.splitlines():
            ys = y.split('\t')
            s = eval(ys[1])
            if not s.isspace():
                tk.append(s)
        tokens = get_clean_code(tk)
    except:
        tokens = re.findall(r"[a-zA-Z0-9]+|[^\sa-zA-Z0-9]|[^_\sa-zA-Z0-9]", line.strip())
    subtokens = []
    labels = []
    indices = []
    for token in tokens:
        curr = re.sub('([a-z0-9])([A-Z])', r'\1 \2', token).split()
        if len(curr) == 0:
            continue
        if len(curr) == 1:
            labels.append(0)
            indices.append(0)
            subtokens.append(curr[0].lower())
            continue
        for s, subtoken in enumerate(curr):
            labels.append(1)
            indices.append(s)
            subtokens.append(curr[s].lower())
    
    return subtokens, labels, indices

def dump_to_file(obj, file):
    with open(file,'w+') as f:
        for el in obj:
            f.write(json.dumps(el)+'\n')

def preproces(diff_filename, msg_filename, lang_filename, output_dir):
    data = list()
    diff_per_file = open(diff_filename,"r").read().split("\n")
    msg_per_file = open(msg_filename,"r").read().split("\n")
    lang_per_file = open(lang_filename,"r").read().split("\n")
    if len(diff_per_file) == len(msg_per_file) and len(msg_per_file) == len(lang_per_file):
        for commit_i in range(len(msg_per_file)):
            commit = dict()
            commit['diff'] = diff_per_file[commit_i]
            commit['msg'] = msg_per_file[commit_i]
            commit['lang'] = lang_per_file[commit_i]
            data.append(commit)
    else:
        logger.warning("{} {} {} dont match".format(len(diff_per_file), len(msg_per_file), len(lang_per_file)))
        exit()

    pattern = re.compile(r'\w+')
    examples = []
    count_none = 0
    with tqdm(total=len(data), desc="build") as pbar:
        for x, i in enumerate(data):
            if x > 1000000000:  # x for debug, set value of x to a small num
                break
            diff = i['diff']
            lang = i['lang'].split()
            if diff == None or i['msg'] == None or i['lang'] == None:
                count_none+=1
                pbar.update(1)
                continue
            diff = diff.replace("<nl> ", "\n")
                        
            ls = diff.splitlines()
            diff_marks = list()
            # other_file = False
            nxt_file = False
            cur_lang = -1
            old_single_lines_ls = list()
            new_single_lines_ls = list()
            old_single_lines = list()
            new_single_lines = list()
            for line in ls:
                if len(line) < 1: # blank line
                    continue
                if line.startswith('ppp ') or line.startswith('mmm '):
                    if (len(old_single_lines) > 0 or len(new_single_lines) > 0) and not nxt_file:
                        old_single_lines_ls.append(old_single_lines)
                        new_single_lines_ls.append(new_single_lines)
                        new_single_lines = list()
                        old_single_lines = list()
                    if line.startswith('ppp '):
                        new_single_lines.append(line)
                    if line.startswith('mmm '):
                        old_single_lines.append(line)
                    nxt_file = True
                else:
                    st = line[0]
                    if nxt_file:
                        cur_lang += 1
                        nxt_file = False
                    if st != '+' and st != '-': # the code not changed 
                        try:
                            old_single_lines.append(line)
                            new_single_lines.append(line)
                        except:
                            print(diff)
                            print(lang)
                            print(cur_lang)
                        diff_marks.append(2)
                    elif st == '-': # the code deleted
                        line = line[1:].strip()
                        old_single_lines.append(line)
                        diff_marks.append(1)
                    elif st == '+': # the code added
                        line = line[1:].strip()
                        new_single_lines.append(line)
                        diff_marks.append(3)

            if len(old_single_lines) > 0 or len(new_single_lines) > 0:
                old_single_lines_ls.append(old_single_lines)
                new_single_lines_ls.append(new_single_lines)
            
            diff_tokens = list()

            for idx, (old_lines, new_lines) in enumerate(zip(old_single_lines_ls, new_single_lines_ls)):
                old_code = '\n'.join(old_lines)
                new_code = '\n'.join(new_lines)
                old_code_subtokens, old_code_subtoken_labels, old_code_subtoken_indices = subtokenize_code(old_code, lang[idx])
                new_code_subtokens, new_code_subtoken_labels, new_code_subtoken_indices = subtokenize_code(new_code, lang[idx])
                span_diff_tokens, _, _ = compute_code_diff_spans(
                    old_code_subtokens, old_code_subtoken_labels, old_code_subtoken_indices, new_code_subtokens, new_code_subtoken_labels, new_code_subtoken_indices)
                
                for token in span_diff_tokens:
                    diff_tokens.append(token)
            
            msg = i['msg'].split()
            # msg = [i for i in msg if i != '' and not i.isspace()]

            # examples.append({'msgtext':i['msg'],'msg_tokens':msg,'difftext':diff, 'diff': diff_tokens})
            examples.append({'diff': diff_tokens, 'msg_token':msg})

            pbar.update(1)
    
    logger.info("{} commits in {} are None;".format(count_none, lang))
    logger.info("load {} commits finished".format(len(data)))
    
    os.makedirs(output_dir, exist_ok=True)
    out_file = diff_filename.split('/')[-1]
    out_file = '.'.join([w for w in out_file.split('.')[:-1]])
    dump_to_file(examples, os.path.join(output_dir, '{}.jsonl'.format(out_file)))
    print(len(examples))

if __name__ == "__main__":
    args = parse_args()
    logger.info(args)

    preproces(args.diff_filename, args.msg_filename, args.lang_filename, args.output_dir)