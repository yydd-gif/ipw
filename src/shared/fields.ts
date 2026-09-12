import type { FieldDef } from './types'

export const PROJECT_FIELD_DEFS: FieldDef[] = [
  { key: 'project_name', label: '项目名称', scope: 'project', required: true },
  { key: 'owner', label: '建设单位', scope: 'project', required: true },
  { key: 'supervisor', label: '监理单位', scope: 'project' },
  { key: 'contractor', label: '施工单位', scope: 'project' },
  { key: 'contract_no', label: '合同号', scope: 'project' },
  { key: 'phase', label: '阶段', scope: 'project', placeholder: '施工 / 试运行 / 验收' },
  { key: 'doc_no', label: '文号', scope: 'project' },
  { key: 'location', label: '工程地点', scope: 'project' },
  { key: 'date', label: '填报日期', scope: 'project', placeholder: 'YYYY-MM-DD' }
]

const SHARED_PROJECT = PROJECT_FIELD_DEFS

export const ITEM_FIELD_SCHEMAS: Record<string, FieldDef[]> = {
  '2.7': [
    ...SHARED_PROJECT,
    { key: 'device_name', label: '设备名称', scope: 'item', required: true },
    { key: 'device_model', label: '规格型号', scope: 'item', required: true },
    { key: 'inspect_date', label: '开箱日期', scope: 'item', required: true, placeholder: 'YYYY-MM-DD' },
    { key: 'inspector', label: '检验人', scope: 'item' },
    { key: 'inspect_result', label: '检验结论', scope: 'item', required: true, multiline: true }
  ],
  '6.2': [
    ...SHARED_PROJECT,
    { key: 'accept_date', label: '验收日期', scope: 'item', required: true, placeholder: 'YYYY-MM-DD' },
    { key: 'accept_conclusion', label: '验收结论', scope: 'item', required: true },
    { key: 'summary', label: '建设概况', scope: 'item', required: true, multiline: true }
  ],
  '8.1': [
    ...SHARED_PROJECT,
    { key: 'cover_date', label: '封面日期', scope: 'item', required: true, placeholder: 'YYYY-MM-DD' },
    { key: 'volume_title', label: '资料标题', scope: 'item', placeholder: '竣工验收资料' }
  ]
}

export function fieldsForItem(code: string): FieldDef[] {
  return ITEM_FIELD_SCHEMAS[code] ?? []
}

export function inputToProjectFields(input: {
  name: string
  owner: string
  supervisor: string
  contractor: string
  contract_no: string
  phase: string
  doc_no: string
  location?: string
  date?: string
}): Record<string, string> {
  return {
    project_name: input.name,
    owner: input.owner,
    supervisor: input.supervisor,
    contractor: input.contractor,
    contract_no: input.contract_no,
    phase: input.phase,
    doc_no: input.doc_no,
    location: input.location ?? '',
    date: input.date ?? ''
  }
}
