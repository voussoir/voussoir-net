import argparse
import base64
import bs4
import copy
import html
import mimetypes
import mistune
import os
import pygments
import pygments.formatters
import pygments.lexers
import pygments.token
import re
import requests
import string
import sys
import traceback

from voussoirkit import pathclass

HTML_TEMPLATE = '''
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>

<style>
{css}
</style>
</head>

<body>
{body}
</body>
</html>
'''.strip()

SLUG_CHARACTERS = string.ascii_lowercase + string.digits + '_'


class SyntaxHighlighting:
    def block_code(self, text, lang):
        inlinestyles = self.options.get('inlinestyles') or False
        linenos = self.options.get('linenos') or False
        return self._block_code(text, lang, inlinestyles, linenos)

    @staticmethod
    def _block_code(text, lang, inlinestyles=False, linenos=False):
        if not lang:
            text = text.strip()
            return f'<pre><code>{mistune.escape(text)}</code></pre>\n'
        try:
            lexer = pygments.lexers.get_lexer_by_name(lang.lower(), stripall=True)
            # if isinstance(lexer, pygments.lexers.PythonLexer):
            #     lexer = pygments.lexers.PythonConsoleLexer()

            # But wait! Why aren't you doing this:
            #     formatter = pygments.formatters.HtmlFormatter(
            #         noclasses=inlinestyles,
            #         linenos=linenos,
            #         cssclass='highlight ' + (lang.lower() if lang else ''),
            #     )
            #     code = pygments.highlight(text, lexer, formatter).decode('utf-8')
            # ??
            elements = []
            for (token, text) in lexer.get_tokens(text):
                if text.isspace():
                    elements.append(text)
                    continue
                css_class = pygments.token.STANDARD_TYPES.get(token, '')
                element = f'<span class="{css_class}">{html.escape(text)}</span>'
                elements.append(element)
            code = ''.join(elements)

            divclass = ['highlight']
            if lang:
                divclass.append(lang.lower())
            divclass = ' '.join(divclass)

            code = f'<div class="{divclass}"><pre>{code}</pre></div>'
            # if lang:
            #     code = code.replace('div class="highlight"', f'div class="highlight {lang.lower()}"')
            # if linenos:
            #     return f'<div class="highlight-wrapper">{code}</div>\n'
            return code
        except Exception:
            traceback.print_exc()
            return f'<pre class="{lang}"><code>{mistune.escape(text)}</code></pre>\n'


class VoussoirRenderer(
        SyntaxHighlighting,
        mistune.Renderer,
    ):
    pass

class VoussoirGrammar(mistune.InlineGrammar):
    larr = re.compile(r'<--')
    rarr = re.compile(r'-->')
    mdash = re.compile(r'--')
    category_tag = re.compile(r'\[tag:([\w\.]+)\]')
    text = re.compile(r'^[\s\S]+?(?=[\\<!\[_*`~\-]|https?:\/\/| {2,}\n|$)')

class VoussoirLexer(mistune.InlineLexer):
    default_rules = copy.copy(mistune.InlineLexer.default_rules)
    default_rules.insert(0, 'mdash')
    default_rules.insert(0, 'larr')
    default_rules.insert(0, 'rarr')
    default_rules.insert(0, 'category_tag')

    def __init__(self, renderer, **kwargs):
        rules = VoussoirGrammar()
        super().__init__(renderer, rules, **kwargs)

    def output_category_tag(self, m):
        qualname = m.group(1)
        tagname = qualname.split('.')[-1]
        return f'<a class="tag_link" data-qualname="{qualname}">[{tagname}]</a>'

    def output_mdash(self, m):
        return '&mdash;'

    def output_rarr(self, m):
        return '&rarr;'

    def output_larr(self, m):
        return '&larr;'

renderer = VoussoirRenderer()
inline = VoussoirLexer(renderer)
VMARKDOWN = mistune.Markdown(renderer=renderer, inline=inline)

# GENERIC HELPERS
################################################################################
def cat_file(path):
    if isinstance(path, pathclass.Path):
        path = path.absolute_path
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

def cat_files(paths):
    if not paths:
        return ''
    if isinstance(paths, str):
        return cat_file(paths)
    content = [cat_file(path) for path in paths]
    return '\n\n'.join(content)

def dump_file(path):
    with open(path, 'rb') as f:
        return f.read()

# SOUP HELPERS
################################################################################
def add_header_anchors(soup):
    '''
    Give each <hX> an <a> to link to it.
    '''
    header_pattern = re.compile(rf'^h[1-6]$')
    used_slugs = set()

    for header in soup.find_all(header_pattern):
        slug = slugify(header.get_text())
        slug = uniqify_slug(slug, used_slugs)

        header['id'] = slug

        new_a = soup.new_tag('a')
        new_a['href'] = '#' + slug
        new_a['class'] = 'header_anchor_link'
        paragraph_symbol = chr(182)
        new_a.append(f' ({paragraph_symbol})')
        header.append(new_a)

def add_toc(soup, max_level=None):
    '''
    Gather up all the header anchors and form a table of contents,
    which will be placed below the first h1 on the page, if the page has an h1.
    '''
    first_h1 = soup.h1
    if not first_h1:
        return

    def new_list(root=False):
        r = bs4.BeautifulSoup('<ol></ol>', 'html.parser')
        if root:
            return r
        return r.ol

    # Official HTML headers only go up to 6.
    if max_level is None:
        max_level = 6

    elif max_level < 1:
        raise ValueError('max_level must be >= 1.')

    header_pattern = re.compile(rf'^h[1-{max_level}]$')

    toc = new_list(root=True)
    toc.ol['id'] = 'table_of_contents'
    toc.ol.append('Table of contents')
    current_list = toc.ol
    current_list['level'] = None

    headers = soup.find_all(header_pattern)
    for header in headers:
        if header == first_h1:
            continue
        # 'hX' -> X
        level = int(header.name[1])

        toc_line = toc.new_tag('li')
        toc_a = toc.new_tag('a')

        toc_a.append(str(header.find(text=True)))
        toc_a['href'] = f'#{header["id"]}'
        toc_line.append(toc_a)

        if current_list['level'] is None:
            current_list['level'] = level

        while level < current_list['level']:
            # Because the sub-<ol> are actually a child of the last
            # <li> of the previous <ol>, we must .parent twice.
            # The second .parent is conditional because if the current
            # list is toc.ol, then parent is a Soup document object, and
            # parenting again would be a mistake. We'll recover from
            # this in just a moment.
            current_list = current_list.parent
            if current_list.name == 'li':
                current_list = current_list.parent
            # If the file has headers in a non-ascending order, like the
            # first header is an h4 and then an h1 comes later, then
            # this while loop would keep attempting to climb the .parent
            # which would take us too far, off the top of the tree.
            # So, if we reach `current_list == toc.ol` then we've
            # reached the root and should stop climbing. At that point
            # we can just snap current_level and use the root list again.
            # In the resulting toc, that initial h4 would have the same
            # toc depth as the later h1 since it never had parents.
            if current_list == toc:
                current_list['level'] = level
                current_list = toc.ol

        if level > current_list['level']:
            # In order to properly render nested <ol>, you're supposed
            # to make the new <ol> a child of the last <li> of the
            # previous <ol>. NOT a child of the prev <ol> directly.
            # Don't worry, .children can never be empty because on the
            # first <li> this condition can never occur, and new <ol>s
            # always receive a child right after being created.
            _l = new_list()
            _l['level'] = level
            final_li = list(current_list.children)[-1]
            final_li.append(_l)
            current_list = _l

        current_list.append(toc_line)

    for ol in toc.find_all('ol'):
        del ol['level']

    first_h1.insert_after(toc.ol)

def add_head_title(soup):
    '''
    Add the <title> element in <head> based on the text of the first <h1>.
    '''
    first_h1 = soup.h1
    if not first_h1:
        return

    text = get_innertext(first_h1)
    title = soup.new_tag('title')
    title.append(text)
    soup.head.append(title)

def embed_images(soup, cache=None):
    '''
    Find <img> srcs and either download the url or load the local file,
    and convert it to a data URI.
    '''
    for element in soup.find_all('img'):
        src = element['src']
        if cache is None:
            cache = {}
        if cache.get(src) is None:
            print('Fetching %s' % src)
            if src.startswith('https://') or src.startswith('http://'):
                response = requests.get(src)
                response.raise_for_status()
                data = response.content
            else:
                data = dump_file(src)
            data = base64.b64encode(data).decode('ascii')
            mime = mimetypes.guess_type(src)[0]
            mime = mime if mime is not None else ''
            uri = f'data:{mime};base64,{data}'
            cache[src] = uri
        else:
            uri = cache[src]
        element['src'] = uri

def get_innertext(element):
    if isinstance(element, bs4.NavigableString):
        return element.string
    else:
        return element.get_text()

def next_element_sibling(element):
    '''
    Like nextSibling but skips NavigableString.
    '''
    while True:
        element = element.nextSibling
        if isinstance(element, bs4.NavigableString):
            continue
        return element

def previous_element_sibling(element):
    while True:
        element = element.previousSibling
        if isinstance(element, bs4.NavigableString):
            continue
        return element

def remove_leading_empty_nodes(element):
    '''
    Code <pre>s often start with an empty span, so this strips it off.
    '''
    children = list(element.children)
    while children:
        if get_innertext(children[0]) == '':
            children.pop(0).extract()
        else:
            break

def slugify(text):
    '''
    Filter text to contain only SLUG_CHARACTERS.
    '''
    text = text.lower()
    text = text.replace(' ', '_')
    text = [c for c in text if c in SLUG_CHARACTERS]
    text = ''.join(text)
    return text

def uniqify_slug(slug, used_slugs):
    '''
    If the given slug has already been used, give it a trailing _2 or _3 etc.
    '''
    count = 2
    try_slug = slug
    while try_slug in used_slugs:
        try_slug = f'{slug}_{count}'
        count += 1
    slug = try_slug
    used_slugs.add(slug)
    return slug

# HTML CLEANERS
################################################################################
def html_replacements(html):
    html = re.sub(r'<style>\s*</style>', '', html)
    html = html.replace(
        '<span class="o">&gt;&gt;</span><span class="o">&gt;</span>',
        '<span>&gt;&gt;&gt;</span>'
    )
    html = html.replace(
        '<span class="o">.</span><span class="o">.</span><span class="o">.</span>',
        '<span>...</span>'
    )
    return html

# SOUP CLEANERS
################################################################################
def fix_argument_call_classes(element):
    '''
    Given a <span class="n"> pointing to a function being called, this fixes
    the classes of all the keyword arguments from being plain names to being
    argument names.
    '''
    # print('INPUT', repr(element))
    paren_depth = 0
    while True:
        element = next_element_sibling(element)
        # print(element, paren_depth)
        innertext = element.get_text()

        if innertext == '(':
            paren_depth += 1

        if innertext == ')':
            paren_depth -= 1

        if 'n' in element['class']:
            last_known_candidate = element

        if 'o' in element['class'] and innertext == '=':
            last_known_candidate['class'].remove('n')
            last_known_candidate['class'].append('narg')

        if paren_depth == 0:
            break

def fix_argument_def_classes(element):
    '''
    Given a <span class="kd">def</span>, fix the function arguments so they are
    a special color like they're SUPPOSED TO BE.
    '''
    # print('INPUT', repr(element))
    do_color = True
    while True:
        element = next_element_sibling(element)
        # print(element)
        innertext = element.get_text()
        if innertext == ')' and next_element_sibling(element).get_text() == ':':
            break

        if innertext == '=':
            do_color = False

        elif innertext == ',':
            do_color = True

        elif do_color:
            if 'n' in element['class']:
                element['class'].remove('n')
                element['class'].append('narg')
            elif 'bp' in element['class']:
                element['class'].remove('bp')
                element['class'].append('narg')
            elif 'o' in element['class'] and innertext in ('*', '**'):
                # Fix *args, the star should not be operator colored.
                element['class'].remove('o')
                element['class'].append('n')

def fix_repl_classes(element):
    '''
    Given a <pre> element, this function detects that this pre contains a REPL
    session when the first line starts with '>>>'.

    For REPL sessions, any elements on an input line (which start with '>>>' or
    '...') keep their styles, while elements on output lines are stripped of
    their styles.

    Of course you can confuse it by having an output which starts with '>>>'
    but that's not the point okay?
    '''
    remove_leading_empty_nodes(element)
    children = list(element.children)
    if not children:
        return

    if get_innertext(children[0]) != '>>>':
        return

    del_styles = None
    for child in children:
        if get_innertext(child).endswith('\n'):
            del_styles = None

        elif del_styles is None:
            del_styles = child.string not in ('>>>', '...')

        if isinstance(child, bs4.NavigableString):
            continue

        if del_styles:
            del child['class']

def fix_leading_pre_spaces(element):
    '''
    I noticed this issue when using code blocks inside of a numbered list.
    The first line would be okay but then the rest of the lines would be
    +1 or +2 spaces indented.
    So this looks for linebreaks inside code blocks, and removes additional
    spaces that come after the linebreak.
    '''
    return
    children = list(element.children)
    for child in children:
        if isinstance(child, bs4.element.NavigableString):
            text = get_innertext(child)
            text = text.split('\n')
            text = [text[0]] + [t.lstrip() for t in text[1:]]
            text = '\n'.join(text)
            child.replace_with(text)

def fix_classes(soup):
    '''
    Because pygments does not conform to my standards of beauty already!
    '''
    for element in soup.find_all('span', {'class': 'k'}):
        if get_innertext(element) in ('def', 'class'):
            element['class'] = ['kd']

    for element in soup.find_all('span', {'class': 'bp'}):
        if get_innertext(element) in ('None', 'True', 'False'):
            element['class'] = ['m']

    for element in soup.find_all('span', {'class': 'o'}):
        if get_innertext(element) in ('.', '(', ')', '[', ']', '{', '}', ';', ','):
            element['class'] = ['n']

    for element in soup.find_all('pre'):
        fix_repl_classes(element)
        fix_leading_pre_spaces(element)

    for element in soup.find_all('span', {'class': 'kd'}):
        if element.get_text() == 'def':
            fix_argument_def_classes(element)

    for element in soup.find_all('span', {'class': 'n'}):
        if get_innertext(element.nextSibling) == '(':
            fix_argument_call_classes(element)

# FINAL MARKDOWNS
################################################################################
def markdown(
        filename,
        *,
        css=None,
        do_embed_images=False,
        image_cache=None,
        return_soup=False,
        templates=None,
    ):
    body = cat_file(filename)

    if templates:
        if isinstance(templates, str):
            templates = [templates]
        for template in templates:
            template = cat_file(template)
            body = template.replace('{body}', body)

    css = cat_files(css)

    body = VMARKDOWN(body)
    html = HTML_TEMPLATE.format(css=css, body=body)

    html = html_replacements(html)

    soup = bs4.BeautifulSoup(html, 'html.parser')
    # Make sure to add_head_title before add_header_anchors so you don't get
    # the paragraph symbol in the <title>.
    add_head_title(soup)
    add_header_anchors(soup)
    add_toc(soup)
    fix_classes(soup)
    if do_embed_images:
        embed_images(soup, cache=image_cache)


    if return_soup:
        return soup

    html = str(soup)
    return html

def markdown_flask(core_filename, port, *args, **kwargs):
    import flask
    from flask import request
    site = flask.Flask(__name__)
    image_cache = {}
    kwargs['image_cache'] = image_cache
    core_filename = pathclass.Path(core_filename, force_sep='/')
    if core_filename.is_dir:
        cwd = core_filename
    else:
        cwd = pathclass.Path('.')

    def handle_path(path):
        if path.extension == '.md':
            return do_md_for(path)

        if path.is_dir:
            atags = []
            for child in path.listdir():
                relative = child.relative_to(cwd, simple=True)
                print(relative)
                a = f'<p><a href="/{relative}">{child.basename}</a></p>'
                atags.append(a)
            page = '\n'.join(atags)
            return page

        try:
            content = open(path.absolute_path, 'rb').read()
        except Exception as exc:
            print(exc)
            flask.abort(404)
        else:
            response = flask.make_response(content)

            mime = mimetypes.guess_type(path.absolute_path)[0]
            if mime:
                response.headers['Content-Type'] = mime

            return response

    def do_md_for(filename):
        html = markdown(filename=filename, *args, **kwargs)
        refresh = request.args.get('refresh', None)
        if refresh is not None:
            refresh = max(float(refresh), 1)
            html += f'<script>setTimeout(function(){{window.location.reload()}}, {refresh * 1000})</script>'
        return html

    @site.route('/')
    def root():
        return handle_path(core_filename)

    @site.route('/<path:path>')
    def other_file(path):
        path = cwd.join(path)
        if path not in cwd:
            flask.abort(404)
        return handle_path(path)

    site.run(host='0.0.0.0', port=port)

# COMMAND LINE
################################################################################
def markdown_argparse(args):
    if args.output_filename:
        md_file = pathclass.Path(args.md_filename)
        output_file = pathclass.Path(args.output_filename)
        if md_file == output_file:
            raise ValueError('md file and output file are the same!')

    kwargs = {
        'filename': args.md_filename,
        'css': args.css,
        'do_embed_images': args.do_embed_images,
        'templates': args.template,
    }

    if args.server:
        return markdown_flask(core_filename=kwargs.pop('filename'), port=args.server, **kwargs)

    html = markdown(**kwargs)

    if args.output_filename:
        f = open(args.output_filename, 'w', encoding='utf-8')
        f.write(html)
        f.close()
        return

    print(html)

def main(argv):
    parser = argparse.ArgumentParser()

    parser.add_argument('md_filename')
    parser.add_argument('--css', dest='css', action='append', default=None)
    parser.add_argument('--template', dest='template', action='append', default=None)
    parser.add_argument('--embed_images', dest='do_embed_images', action='store_true')
    parser.add_argument('-o', '--output', dest='output_filename', default=None)
    parser.add_argument('--server', dest='server', type=int, default=None)
    parser.set_defaults(func=markdown_argparse)

    args = parser.parse_args(argv)
    return args.func(args)

if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
