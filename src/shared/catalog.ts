import type { CatalogItem, CatalogVolume, FieldDef, Importance, ProjectType } from './types'
import { ITEM_FIELD_SCHEMAS, PROJECT_FIELD_DEFS } from './fields'

const ALL: ProjectType[] = ['engineering', 'gov_it', 'hybrid']
const ENG: ProjectType[] = ['engineering', 'hybrid']
const GOV: ProjectType[] = ['gov_it', 'hybrid']

function row(
  code: string,
  title: string,
  volumeId: string,
  produceType: CatalogItem['produceType'],
  opts: {
    required?: boolean
    appliesTo?: ProjectType[]
    importance?: Importance
    templateFile?: string
    stubNote?: string
  } = {}
): CatalogItem {
  const required = opts.required ?? false
  const fields: FieldDef[] | undefined =
    produceType === 'template' ? ITEM_FIELD_SCHEMAS[code] : undefined
  return {
    code,
    title,
    volumeId,
    produceType,
    required,
    appliesTo: opts.appliesTo ?? ALL,
    importance: opts.importance ?? (required ? 'important' : produceType === 'template' ? 'normal' : 'general'),
    templateFile: opts.templateFile,
    fields,
    stubNote: opts.stubNote
  }
}

export const CATALOG_VOLUMES: CatalogVolume[] = [
  { id: '1', code: '01', title: '依据', folder: '01_依据分册', appliesTo: ALL },
  { id: '2', code: '02', title: '过程', folder: '02_过程分册', appliesTo: ALL },
  { id: '3', code: '03', title: '图纸', folder: '03_图纸分册', appliesTo: ALL },
  { id: '4', code: '04', title: '变更', folder: '04_变更分册', appliesTo: ALL },
  { id: '5', code: '05', title: '初步验收与试运行', folder: '05_初步验收与试运行', appliesTo: GOV },
  { id: '6', code: '06', title: '竣工验收报告', folder: '06_竣工验收报告', appliesTo: ALL },
  { id: '7', code: '07', title: '竣工验收分册', folder: '07_竣工验收分册', appliesTo: GOV },
  { id: '8', code: '08', title: '封面页', folder: '08_封面页', appliesTo: ALL }
]

export const CATALOG_ITEMS: CatalogItem[] = [
  row('1.1', '立项批复文件', '1', 'upload', { importance: 'normal' }),
  row('1.2', '合同', '1', 'upload', { required: true, importance: 'important' }),
  row('1.3', '中标通知书', '1', 'upload', { importance: 'normal' }),

  row('2.1', '开工报审表', '2', 'template', { appliesTo: ENG, importance: 'normal' }),
  row('2.2', '项目经理授权书及法定代表人授权书', '2', 'template', { appliesTo: ENG, importance: 'normal' }),
  row('2.3', '施工组织方案报审表', '2', 'template', { appliesTo: ENG, importance: 'normal' }),
  row('2.4', '施工组织方案', '2', 'template', { appliesTo: ENG, importance: 'normal' }),
  row('2.5', '工程开工令', '2', 'template', { appliesTo: ENG, importance: 'normal' }),
  row('2.6', '材料设备进场报验', '2', 'upload', { required: true, importance: 'important' }),
  row('2.7', '设备开箱检验记录', '2', 'template', {
    required: true,
    importance: 'important',
    templateFile: '2.7_设备开箱检验记录.docx'
  }),
  row('2.8', '设备安装记录', '2', 'template', { required: true, importance: 'important' }),
  row('2.9', '系统调试记录', '2', 'upload', { required: true, importance: 'important' }),
  row('2.10', '施工日志', '2', 'template', { importance: 'normal' }),
  row('2.11', '项目月报', '2', 'upload', { importance: 'general' }),
  row('2.12', '项目周报', '2', 'upload', { importance: 'general' }),
  row('2.13', '过程质量评定资料', '2', 'upload', { required: true, importance: 'important' }),

  row('3.1', '竣工图纸', '3', 'upload', { importance: 'normal' }),
  row('3.2', '设计变更图纸', '3', 'upload', { importance: 'general' }),
  row('3.3', '系统拓扑与部署图', '3', 'upload', { appliesTo: GOV, importance: 'normal' }),

  row('4.1', '变更申请与审批', '4', 'upload', { importance: 'normal' }),
  row('4.2', '现场签证', '4', 'upload', { importance: 'general' }),

  row('5.1', '初步验收申请', '5', 'upload', { required: true, appliesTo: GOV, importance: 'important' }),
  row('5.2', '试运行方案', '5', 'template', { appliesTo: GOV, importance: 'normal' }),
  row('5.3', '试运行记录', '5', 'template', { appliesTo: GOV, importance: 'normal' }),
  row('5.4', '试运行报告', '5', 'upload', { required: true, appliesTo: GOV, importance: 'important' }),
  row('5.5', '问题整改闭环', '5', 'upload', { appliesTo: GOV, importance: 'general' }),
  row('5.6', '用户培训记录', '5', 'upload', { required: true, appliesTo: GOV, importance: 'important' }),
  row('5.7', '用户确认书', '5', 'upload', { required: true, appliesTo: GOV, importance: 'important' }),
  row('5.8', '初步验收意见', '5', 'upload', { required: true, appliesTo: GOV, importance: 'important' }),
  row('5.9', '初步验收会议纪要', '5', 'upload', { required: true, appliesTo: GOV, importance: 'important' }),

  row('6.1', '报告封面', '6', 'template', { importance: 'normal' }),
  row('6.2', '竣工验收报告', '6', 'template', {
    required: true,
    importance: 'important',
    templateFile: '6.2_竣工验收报告.docx'
  }),
  row('6.3', '报告目录', '6', 'template', { importance: 'general' }),
  row('6.4', '验收结论', '6', 'template', { importance: 'normal' }),

  row('7.1', '项目建设总结', '7', 'template', { required: true, appliesTo: GOV, importance: 'important' }),
  row('7.2', '软硬件清单', '7', 'template', { required: true, appliesTo: GOV, importance: 'important' }),
  row('7.3', '系统测试报告', '7', 'template', { appliesTo: GOV, importance: 'normal' }),
  row('7.4', '安全测评报告', '7', 'upload', { required: true, appliesTo: GOV, importance: 'important' }),
  row('7.5', '密码测评与等保材料', '7', 'upload', { required: true, appliesTo: GOV, importance: 'important' }),
  row('7.6', '培训教材', '7', 'template', { required: true, appliesTo: GOV, importance: 'important' }),
  row('7.7', '操作手册', '7', 'template', { required: true, appliesTo: GOV, importance: 'important' }),
  row('7.8', '维护手册', '7', 'template', { required: true, appliesTo: GOV, importance: 'important' }),
  row('7.9', '源代码及开发文档', '7', 'template', { required: true, appliesTo: GOV, importance: 'important' }),
  row('7.10', '竣工验收申请', '7', 'template', { required: true, appliesTo: GOV, importance: 'important' }),
  row('7.11', '竣工验收意见', '7', 'template', { required: true, appliesTo: GOV, importance: 'important' }),

  row('8.1', '总封面', '8', 'template', {
    importance: 'normal',
    templateFile: '8.1_总封面.docx'
  }),
  row('8.2', '总目录', '8', 'template', { importance: 'normal' }),
  row('8.3', '分册隔页', '8', 'template', { importance: 'general' })
]

export { PROJECT_FIELD_DEFS }

export function itemApplies(item: CatalogItem, type: ProjectType): boolean {
  return item.appliesTo.includes(type)
}

export function volumeApplies(volume: CatalogVolume, type: ProjectType): boolean {
  return volume.appliesTo.includes(type)
}

export function itemsForProjectType(type: ProjectType): CatalogItem[] {
  return CATALOG_ITEMS.filter((item) => itemApplies(item, type))
}

export function volumesForProjectType(type: ProjectType): CatalogVolume[] {
  return CATALOG_VOLUMES.filter((volume) => volumeApplies(volume, type))
}

export function getCatalogItem(code: string): CatalogItem | undefined {
  return CATALOG_ITEMS.find((item) => item.code === code)
}

export function getVolume(id: string): CatalogVolume | undefined {
  return CATALOG_VOLUMES.find((volume) => volume.id === id)
}

export function itemFolderName(item: CatalogItem): string {
  return `${item.code}_${item.title}`
}

export function treeFillDot(importance: Importance, fillStatus: string): 'empty' | 'draft' | 'complete' | 'error' {
  if (fillStatus === 'error') return 'error'
  if (fillStatus === 'complete') return 'complete'
  if (fillStatus === 'draft') return 'draft'
  if (importance === 'important' && fillStatus === 'empty') return 'error'
  return 'empty'
}
