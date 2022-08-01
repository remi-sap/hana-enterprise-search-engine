'''Creates SQL commands from tables'''
from __future__ import annotations
from copy import deepcopy
import convert


ESH_CONFIG_TEMPLATE = {
    'uri': '~/$metadata/EntitySets',
    'method': 'PUT',
    'content': {
        'Fullname': '',
        'EntityType': {
            '@EnterpriseSearch.enabled': True,
            '@Search.searchable': True,
            '@EnterpriseSearchHana.identifier': 'VORGANG_MODEL',
            '@EnterpriseSearchHana.passThroughAllAnnotations': True,
            'Properties': []}}}

'''
{
    'Name': '_ID',
    '@EnterpriseSearch.key': True,
    '@Search.defaultSearchElement': True,
    '@UI.hidden': True
}
'''
class Constants(object):
    table_name = 'table_name'
    columns = 'columns'
    type = 'type'
    length = 'length'
    precision = 'precision'
    scale = 'scale'
    srid = 'srid'

def get_columns(table):
    columns = []
    for prop_name, prop in table[Constants.columns].items():
        if 'isVirtual' in prop and prop['isVirtual']:
            continue
        if Constants.length in prop:
            column_type = f'{prop[Constants.type]}({prop[Constants.length]})'
        elif Constants.srid in prop:
            column_type = f'{prop[Constants.type]}({prop[Constants.srid]})'
        elif Constants.precision in prop and Constants.scale in prop:
            column_type = f'{prop[Constants.type]}({prop[Constants.precision]},{prop[Constants.scale]})'
        else:
            column_type = prop[Constants.type]
        if 'pk' in table and table['pk'] == prop_name:
            suffix = ' PRIMARY KEY'
        else:
            suffix = ''
        cl = f'"{prop_name}" {column_type}{suffix}'
        columns.append(cl)
    return columns

def sequence(i = 0, prefix = '', fill = 3):
    while True:
        if prefix:
            yield f'{prefix}{str(i).zfill(fill)}'
        else:
            yield i
        i += 1

def sequenceInt(i = 10, step = 10):
    while True:
        yield i
        i += step

class ColumnView:
    """Column view definition"""
    def __init__(self, view_name: str, anchor_table_name: str) -> None:
        self.view_name = view_name
        self.anchor_table_name = anchor_table_name
        self.join_index = {}
        self.view_attribute = []
        self.join_conditions = []
        self.join_path = {}
        self.table(anchor_table_name)
        self.join_path_id_gen = sequence(1, 'JP', 3)
        self.join_condition_id_gen = sequence(1, 'JC', 3)
        self.ui_position_gen = sequenceInt()
    def table(self, table_name):
        if not table_name in self.join_index:
            self.join_index[table_name] = 0
        else:
            self.join_index[table_name] += 1
        return (table_name, self.join_index[table_name])

    def add_join_condition(self, join_path_id, join_index_from, column_name_from, join_index_to, column_name_to):
        join_condition_id = next(self.join_condition_id_gen)
        self.join_conditions.append((join_condition_id, self.get_join_index_name(join_index_from),\
            column_name_from, self.get_join_index_name(join_index_to), column_name_to))
        if join_path_id in self.join_path:
            self.join_path[join_path_id].add(join_condition_id)
        else:
            self.join_path[join_path_id] = set([join_condition_id])

    @staticmethod
    def get_join_index_name(join_index):
        table_name, index = join_index
        if index == 0:
            return table_name
        else:
            return f'{table_name}.temp{str(index).zfill(2)}'

    def get_sql_statement(self):
        v  = f'create or replace column view "{self.view_name}" with parameters (indexType=6,\n'
        for join_index in self.join_index:
            v += f'joinIndex="{join_index}",joinIndexType=0,joinIndexEstimation=0,\n'
        for jc in self.join_conditions:
            v += f'joinCondition=(\'{jc[0]}\',"{jc[1]}","{jc[2]}","{jc[3]}","{jc[4]}",\'\',81,0),\n'
        for jp_name, jp_conditions in self.join_path.items():
            v += f"joinPath=('{jp_name}','{','.join(sorted(list(jp_conditions)))}'),\n"
        for view_prop_name, table_name, table_prop_name, join_path_id in self.view_attribute:
            v += f"viewAttribute=('{view_prop_name}',\"{table_name}\",\"{table_prop_name}\",'{join_path_id}'"\
                +",'default','attribute'),\n"
        v += f"view=('default',\"{self.anchor_table_name}\"),\n"
        v += "defaultView='default',\n"
        v += 'OPTIMIZEMETAMODEL=0,\n'
        v += "'LEGACY_MODE' = 'TRUE')"
        return v

def tables_dd(tables):
    return [f'create table "{t[Constants.table_name]}" ( {", ".join(get_columns(t))} )'\
        for t in tables.values()]

def search_dd(schema_name, mapping, views):
    views_dd = []
    esh_configs = []
    for view in views:
        anchor_entity = mapping['entities'][view['entity_name']]
        anchor_table_name = anchor_entity['table_name']
        view_name = view['view_name']
        cv = ColumnView(view_name, anchor_table_name)
        anchor_join_index = (anchor_table_name, 0)
        esh_config = deepcopy(ESH_CONFIG_TEMPLATE)
        if 'annotations' in mapping['tables'][anchor_table_name]:
            annotations = mapping['tables'][anchor_table_name]['annotations']
            esh_config['content']['EntityType'] |= annotations
            # for UI5 enterprise search UI to work
            if '@EndUserText.Label' in annotations and not '@SAP.Common.Label' in annotations:
                esh_config['content']['EntityType']['@SAP.Common.Label'] = annotations['@EndUserText.Label']
        esh_config['content']['Fullname'] = f'{schema_name}/{view_name}'
        esh_config['content']['EntityType']['@EnterpriseSearchHana.identifier'] = view['odata_name']
        esh_config_properties = []
        traverse_view_elements(cv, esh_config_properties, mapping, view, anchor_entity, anchor_join_index)
        views_dd.append(cv.get_sql_statement())
        esh_config['content']['EntityType']['Properties'].extend(esh_config_properties)
        esh_configs.append(esh_config)

    return {'views': views_dd, 'eshConfig':esh_configs}


def add_view_column(cv, esh_config_properties, mapping, table_name, join_index, join_path_id,\
    view_column_name, table_column_name, annotations):
    cv.view_attribute.append((view_column_name, \
        cv.get_join_index_name(join_index), table_column_name, join_path_id))
    # ESH config
    col_conf = {'Name': view_column_name}
    if annotations:
        col_conf |= annotations
    elif 'annotations' in mapping['tables'][table_name]['columns'][table_column_name]:
        col_conf |= mapping['tables'][table_name]['columns'][table_column_name]['annotations']
    # for UI5 enterprise search UI to work
    is_enteprise_search_key = \
        not join_path_id and table_column_name == mapping['tables'][table_name]['pk']
    if is_enteprise_search_key:
        col_conf['@EnterpriseSearch.key'] = True
        col_conf['@UI.hidden'] = True
    else:
        col_conf['@Search.defaultSearchElement'] = True
    if annotations and '@EndUserText.Label' in annotations and '@SAP.Common.Label' not in annotations:
        col_conf['@SAP.Common.Label'] = annotations['@EndUserText.Label']
    if not join_path_id and not is_enteprise_search_key:
        col_conf['@UI.identification'] = [{'position': next(cv.ui_position_gen)}]
    esh_config_properties.append(col_conf)

def traverse_view_elements(cv: ColumnView, esh_config_properties, mapping, view_pos, entity_pos, \
    join_index, join_path_id = ''):
    table_name = join_index[0]
    if 'elements' in view_pos:
        for prop_name, prop in view_pos['elements'].items():
            entity_prop = entity_pos['elements'][prop_name]
            if 'items' in prop:
                next_entity_pos = entity_prop['items']
                next_view_pos = prop['items']
                if join_path_id:
                    jp_id = join_path_id
                else:
                    jp_id = next(cv.join_path_id_gen)
                target_table_name = next_entity_pos['table_name']
                target_join_index = cv.table(target_table_name)
                source_key = mapping['tables'][table_name]['pk']
                target_key = mapping['tables'][target_table_name]['pkParent']
                cv.add_join_condition(jp_id, join_index, source_key\
                    , target_join_index, target_key )
                traverse_view_elements(cv, esh_config_properties, mapping,\
                    next_view_pos, next_entity_pos, target_join_index, jp_id)
            elif 'elements' in prop:
                traverse_view_elements(cv, esh_config_properties, mapping,\
                    prop, entity_prop, join_index, join_path_id)
            else:
                annotations = prop['annotations'] if 'annotations' in prop else {}
                add_view_column(cv, esh_config_properties, mapping, table_name, join_index, join_path_id,\
                    prop['view_column_name'], entity_prop['column_name'], annotations)            
    else:
        annotations = view_pos['annotations'] if 'annotations' in view_pos else {}
        add_view_column(cv, esh_config_properties, mapping, table_name, join_index, join_path_id,\
            view_pos['view_column_name'], '_VALUE', annotations)            

def mapping_to_ddl(mapping, schema_name):
    tables = tables_dd(mapping['tables'])
    sdd = search_dd(schema_name, mapping, [v for v in mapping['views'].values()])
    return {'tables': tables, 'views': sdd['views'], 'eshConfig':sdd['eshConfig']}
