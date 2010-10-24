#This file is part of Tryton.  The COPYRIGHT file at the top level
#of this repository contains the full copyright notices and license terms.
"Nereid CMS"

from nereid.templating import render_template
from nereid.threading import local
from nereid.helpers import slugify
from nereid.exceptions import NotFound
from trytond.pyson import Eval
from trytond.model import ModelSQL, ModelView, fields

class CMSMenus(ModelSQL, ModelView):
    "Nereid CMS Menus"
    _name = 'nereid.cms.menus'
    _description = __doc__

    name = fields.Char('Name', size=100, required=True, select=1)
    unique_identifier = fields.Char(
        'Unique Identifier', 
        required=True,
        on_change_with=['name', 'unique_identifier'],
        select=1
    )
    description = fields.Text('Description')
    website = fields.Many2One('nereid.website', 'WebSite', select=2)
    active = fields.Boolean('Active')

    model = fields.Many2One(
        'ir.model', 
        'Open ERP Model', 
        required=True
    )
    parent_field = fields.Many2One('ir.model.field', 'Parent',
        domain=[
            ('model', '=', Eval('model')),
            ('ttype', '=', 'many2one')
        ], required=True
    )
    children_field = fields.Many2One('ir.model.field', 'Children',
        domain=[
            ('model', '=', Eval('model')),
            ('ttype', '=', 'one2many')
        ], required=True
    )
    uri_field = fields.Many2One('ir.model.field', 'URI Field',
        domain=[
            ('model', '=', Eval('model')),
            ('ttype', '=', 'char')
        ], required=True
    )
    identifier_field = fields.Many2One('ir.model.field', 'Identifier Field',
        domain=[
            ('model', '=', Eval('model')),
            ('ttype', '=', 'char')
        ], required=True
    )

    def default_active(self, cursor, user, context=None):
        """
        By Default the Menu is active
        """
        return True

    def __init__(self):
        super(CMSMenus, self).__init__()
        self._sql_constraints += [
            ('unique_identifier', 'UNIQUE(unique_identifier, website)',
                'The Unique Identifier of the Menu must be unique.'),
        ]

    def _menu_item_to_dict(self, cursor, user, menu, menu_item):
        """
        :param menu_item: BR of the menu item
        :param menu: BR of the menu set
        """
        return {
                'name' : getattr(menu_item, menu.identifier_field.name),
                'uri' : getattr(menu_item, menu.uri_field.name),
            }

    def _generate_menu_tree(self, cursor, user, 
            menu, menu_item, context):
        """
        :param menu: BrowseRecord of the Menu
        :param menu_item: BrowseRecord of the root menu_item
        :param context: Tryton Context
        """
        result = {'children' : [ ]}
        result.update(
            self._menu_item_to_dict(
                cursor, user, menu, menu_item
                )
            )
        # If children exist iteratively call _generate_..
        children = getattr(menu_item, menu.children_field.name)
        if children:
            for child in children:
                result['children'].append(
                    self._generate_menu_tree(
                        cursor, user, menu, child, context
                    )
                )
        return result

    def _menu_for(self, cursor, user, identifier,
        ident_field_value, context=None):
        """
        Returns a dictionary of menu tree

        :param cursor: Database Cursor
        :param user: ID of the user
        :param identifier: The unique identifier from which the menu
                has to be chosen
        :param ident_field_value: The value of the field that has to be 
                looked up on model with search on ident_field
        :param context: Tryton context
        """
        # First pick up the menu through identifier
        menu_id = self.search(cursor, user, [
            ('unique_identifier', '=', identifier)
            ], limit=1, context=context)
        if not menu_id:
            # TODO: May be raise an error ? Look at some other app
            # how this is handled
            return None
        menu = self.browse(cursor, user, menu_id[0], context)

        # Get the data from the model
        menu_item_object = self.pool.get(menu.model.model)
        menu_item_id = menu_item_object.search(cursor, user, 
            [(menu.identifier_field.name, '=', ident_field_value)],
            limit=1, context=context
            )
        if not menu_item_id:
            # Raise error ?
            return None
        root_menu_item = menu_item_object.browse(
            cursor, user, menu_item_id[0], context
            )
        return self._generate_menu_tree(
            cursor, user, menu, root_menu_item, context
            )

    def menu_for(self, request):
        """
        Template context processor method

        This method could be used to fetch a specific menu for like
        a wrapper from the templates

        From the templates the usage would be:

        `menu_for('category_menu', 'all_products')`
        """
        def wrapper(identifier, ident_field_value):
            return self._menu_for(
                local.transaction.cursor,
                request.tryton_user.id,
                identifier, ident_field_value,
                request.tryton_context
            )
        return {'menu_for': wrapper}

    def on_change_with_unique_identifier(self, cursor, 
                                        user, vals, context=None):
        if vals.get('name'):
            if not vals.get('unique_identifier'):
                vals['unique_identifier'] = slugify(vals['name'])
            return vals['unique_identifier']

CMSMenus()


class CMSMenuitems(ModelSQL, ModelView):
    "Nereid CMS Menuitems"
    _name = 'nereid.cms.menuitems'
    _description = __doc__
    _rec_name = 'unique_name'
    
    title = fields.Char(
        'Title', size=100, 
        required=True, select=1
        )
    unique_name = fields.Char(
        'Unique Name', 
        required=True, 
        on_change_with=['title', 'unique_name'],
        select=1,
        )
    link = fields.Char('Link', size=255,)
    parent = fields.Many2One('nereid.cms.menuitems', 'Parent Menuitem',)
    child_id = fields.One2Many(
        'nereid.cms.menuitems', 
        'parent', 
        string='Child Menu Items'
    )
    active = fields.Boolean('Active')
    sequence = fields.Integer('Sequence', required=True,)

    def default_active(self, cursor, user, context=None ):
        return True

    def check_recursion(self, cursor, user, ids):
        """
        Check the recursion beyond a certain limit.
      
        :param cursor: Database Cursor
        :param user: ID of User
        :param ids: ID of Current Record

        : return: True
        """
        level = 100
        while len(ids):
            cursor.execute('select distinct parent from nereid_cms_menuitems \
                                        where id in (' + ','.join(
                                                        map(str, ids)
                                                        ) + ')')
            ids = filter(None, map(lambda x:x[0], cursor.fetchall()))
            if not level:
                return False
            level -= 1
        return True

    def __init__(self):
        super(CMSMenuitems, self).__init__()
        self._constraints += [
            ('check_recursion', 'wrong_recursion')
        ]
        self._error_messages.update({
            'wrong_recursion': 
            'Error ! You can not create recursive menuitems.',
        })
        self._order.insert(0, ('sequence', 'ASC'))
    
    def on_change_with_unique_name(self, cursor, 
                                        user, vals, context=None):
        if vals.get('title'):
            if not vals.get('unique_name'):
                vals['unique_name'] = slugify(vals['title'])
            return vals['unique_name']

CMSMenuitems()


class ArticleCategory(ModelSQL, ModelView):
    "Article Categories"
    _name = 'nereid.article.category'
    _description = __doc__
    _rec_name = 'unique_name'

    title = fields.Char('Title', size=100, required=True,)
    unique_name = fields.Char(
        'Unique Name', 
        required=True,
        on_change_with=['title', 'unique_name'],
    )
    active = fields.Boolean('Active',)
    description = fields.Text('Description',)
    template = fields.Many2One('nereid.template', 'Template', required=True)
    articles = fields.One2Many('nereid.cms.article', 'category', 'Articles')

    def default_active(self, cursor, user, context=None ):
        'Return True' 
        return True
    
    def __init__(self):
        super(ArticleCategory, self).__init__()
        self._sql_constraints += [
            ('unique_name', 'UNIQUE(unique_name)',
                'The Unique Name of the Category must be unique.'),
        ]
    
    def on_change_with_unique_name(self, cursor, 
                                        user, vals, context=None):
        if vals.get('title'):
            if not vals.get('unique_name'):
                vals['unique_name'] = slugify(vals['title'])
            return vals['unique_name']

    def render(self, cursor, request, arguments=None):
        """
        Renders the category
        """
        uri = arguments.get('uri', None)
        user = request.tryton_user.id
        if not uri:
            return NotFound()
        category_ids = self.search(
            cursor, user, 
            [('uri', '=', uri)], context = request.tryton_context
            )
        if not category_ids:
            return NotFound()
        category = self.browse(
            cursor, user, category_ids[0], request.tryton_context
            )
        template_name = article.template.name
        html = render_template(template_name, category=category)
        return local.application.response_class(
            html, mimetype='text/html'
            )

ArticleCategory()


class CMSArticles(ModelSQL, ModelView):
    "CMS Articles"
    _name = 'nereid.cms.article'
    _inherits = {'nereid.flatpage': 'flatpage_id'}
    
    flatpage_id = fields.Many2One(
        'nereid.flatpage',
        'Flatpage', 
        required=True
    )
    active = fields.Boolean('Active')
    category = fields.Many2One(
        'nereid.article.category', 
        'Category',
        required=True,
    )
    image = fields.Many2One('nereid.static.file', 'Image')
    author = fields.Many2One('res.user', 'Author',)
    create_date = fields.DateTime('Created Date')
    published_on = fields.DateTime('Published On')
    sequence= fields.Integer('Sequence', required=True,)

    def __init__(self):
        super(CMSArticles, self).__init__()
        self._order.insert(0, ('sequence', 'ASC'))

    def default_active(self, cursor, user, context=None ):
        return True
    
    def default_author(self, cursor, user, context=None ):
        return user
    
    def default_published_on(self, cursor, user, context=None ):
        date_obj = self.pool.get('ir.date')
        return date_obj.today(cursor, user, context=context)
    
    def render(self, cursor, request, arguments=None):
        """
        Renders the template
        """
        uri = arguments.get('uri', None)
        if not uri:
            return NotFound()
        article_ids = self.search(
            cursor, request.tryton_user.id, 
            [('uri', '=', uri)], context = request.tryton_context
            )
        if not article_ids:
            return NotFound()
        article = self.browse(cursor, request.tryton_user.id, 
                               article_ids[0], 
                               context = request.tryton_context)
        template_name = article.template.name
        html = render_template(template_name, article=article)
        return local.application.response_class(html, 
                                                mimetype='text/html')
        
CMSArticles()
