import type { CatalogItem, CatalogVolume, ProjectType } from './types'

const ALL: ProjectType[] = ['engineering', 'gov_it', 'hybrid']
const ENG: ProjectType[] = ['engineering', 'hybrid']
const GOV: ProjectType[] = ['gov_it', 'hybrid']

export const CATALOG_VOLUMES: CatalogVolume[] = [
  { id: '1', code: '01', title: '依据分册', folder: '01_依据分册', appliesTo: ALL },
  { id: '2', code: '02', title: '过程分册', folder: '02_过程分册', appliesTo: ALL },
  { id: '3', code: '03', title: '图纸分册', folder: '03_图纸分册', appliesTo: ALL },
  { id: '4', code: '04', title: '变更分册', folder: '04_变更分册', appliesTo: ALL },
  {
    id: '5',
    code: '05',
    title: '初步验收与试运行（政务信息化）',
    folder: '05_初步验收与试运行',
    appliesTo: GOV
  },
  {
    id: '6',
    code: '06',
    title: '竣工验收（普通/工程）',
    folder: '06_竣工验收_普通工程',
    appliesTo: ALL
  },
  {
    id: '7',
    code: '07',
    title: '竣工验收（政务信息化）',
    folder: '07_竣工验收_政务信息化',
    appliesTo: GOV
  }
]

export const CATALOG_ITEMS: CatalogItem[] = [
  // 1 依据分册 — mostly uploads; 1.2 合同 required
  { code: '1.1', title: '立项批复文件', volumeId: '1', produceType: 'upload', required: false, appliesTo: ALL },
  { code: '1.2', title: '合同', volumeId: '1', produceType: 'upload', required: true, appliesTo: ALL },
  { code: '1.3', title: '中标通知书', volumeId: '1', produceType: 'upload', required: false, appliesTo: ALL },
  { code: '1.4', title: '设计文件及批复', volumeId: '1', produceType: 'upload', required: false, appliesTo: ALL },
  { code: '1.5', title: '开工报告', volumeId: '1', produceType: 'upload', required: false, appliesTo: ALL },

  // 2 过程分册 — 2.1–2.5 为开工报审/授权/施工组织方案等上传件（工程/混合选填）
  { code: '2.1', title: '开工报审表', volumeId: '2', produceType: 'upload', required: false, appliesTo: ENG },
  {
    code: '2.2',
    title: '项目经理授权书及法定代表人授权书',
    volumeId: '2',
    produceType: 'upload',
    required: false,
    appliesTo: ENG
  },
  { code: '2.3', title: '施工组织方案报审表', volumeId: '2', produceType: 'upload', required: false, appliesTo: ENG },
  { code: '2.4', title: '施工组织方案', volumeId: '2', produceType: 'upload', required: false, appliesTo: ENG },
  { code: '2.5', title: '工程开工令', volumeId: '2', produceType: 'upload', required: false, appliesTo: ENG },
  { code: '2.6', title: '材料设备进场报验', volumeId: '2', produceType: 'upload', required: true, appliesTo: ALL },
  {
    code: '2.7',
    title: '设备开箱检验记录',
    volumeId: '2',
    produceType: 'template',
    required: true,
    appliesTo: ALL,
    templateFile: '2.7_设备开箱检验记录.docx'
  },
  {
    code: '2.8',
    title: '设备安装记录',
    volumeId: '2',
    produceType: 'template',
    required: true,
    appliesTo: ALL,
    templateFile: '2.8_设备安装记录.docx'
  },
  { code: '2.9', title: '系统调试记录', volumeId: '2', produceType: 'upload', required: true, appliesTo: ALL },
  {
    code: '2.10',
    title: '施工日志',
    volumeId: '2',
    produceType: 'template',
    required: false,
    appliesTo: ALL,
    templateFile: '2.10_施工日志.docx'
  },
  {
    code: '2.11',
    title: '项目月报',
    volumeId: '2',
    produceType: 'derived',
    required: false,
    appliesTo: ALL,
    templateFile: '2.11_项目月报.docx'
  },
  {
    code: '2.12',
    title: '项目周报',
    volumeId: '2',
    produceType: 'derived',
    required: false,
    appliesTo: ALL,
    templateFile: '2.12_项目周报.docx'
  },
  { code: '2.13', title: '过程质量评定资料', volumeId: '2', produceType: 'upload', required: true, appliesTo: ALL },

  // 3 图纸分册 — uploads
  { code: '3.1', title: '竣工图纸', volumeId: '3', produceType: 'upload', required: false, appliesTo: ALL },
  { code: '3.2', title: '设计变更图纸', volumeId: '3', produceType: 'upload', required: false, appliesTo: ALL },
  { code: '3.3', title: '系统拓扑与部署图', volumeId: '3', produceType: 'upload', required: false, appliesTo: GOV },

  // 4 变更分册 — uploads if any
  { code: '4.1', title: '变更申请与审批', volumeId: '4', produceType: 'upload', required: false, appliesTo: ALL },
  { code: '4.2', title: '现场签证', volumeId: '4', produceType: 'upload', required: false, appliesTo: ALL },

  // 5 初步验收与试运行（政务信息化）required 5.1/5.4/5.6/5.7/5.8/5.9
  { code: '5.1', title: '初步验收申请', volumeId: '5', produceType: 'upload', required: true, appliesTo: GOV },
  { code: '5.2', title: '试运行方案', volumeId: '5', produceType: 'upload', required: false, appliesTo: GOV },
  { code: '5.3', title: '试运行记录', volumeId: '5', produceType: 'upload', required: false, appliesTo: GOV },
  { code: '5.4', title: '试运行报告', volumeId: '5', produceType: 'upload', required: true, appliesTo: GOV },
  { code: '5.5', title: '问题整改闭环', volumeId: '5', produceType: 'upload', required: false, appliesTo: GOV },
  { code: '5.6', title: '用户培训记录', volumeId: '5', produceType: 'upload', required: true, appliesTo: GOV },
  { code: '5.7', title: '用户确认书', volumeId: '5', produceType: 'upload', required: true, appliesTo: GOV },
  { code: '5.8', title: '初步验收意见', volumeId: '5', produceType: 'upload', required: true, appliesTo: GOV },
  { code: '5.9', title: '初步验收会议纪要', volumeId: '5', produceType: 'upload', required: true, appliesTo: GOV },

  // 6 竣工验收（普通/工程）6.2 required; 6.1 engineering optional
  {
    code: '6.1',
    title: '工程竣工报告',
    volumeId: '6',
    produceType: 'upload',
    required: false,
    appliesTo: ENG
  },
  {
    code: '6.2',
    title: '竣工验收报告',
    volumeId: '6',
    produceType: 'template',
    required: true,
    appliesTo: ALL,
    templateFile: '6.2_竣工验收报告.docx'
  },

  // 7 竣工验收（政务信息化）
  {
    code: '7.1',
    title: '项目建设总结',
    volumeId: '7',
    produceType: 'template',
    required: true,
    appliesTo: GOV,
    templateFile: '7.1_项目建设总结.docx'
  },
  {
    code: '7.2',
    title: '软硬件清单',
    volumeId: '7',
    produceType: 'template',
    required: true,
    appliesTo: GOV,
    templateFile: '7.2_软硬件清单.docx'
  },
  {
    code: '7.4',
    title: '安全测评报告',
    volumeId: '7',
    produceType: 'derived',
    required: true,
    appliesTo: GOV,
    stubNote: '后期自动生成'
  },
  {
    code: '7.5',
    title: '密码测评与等保材料',
    volumeId: '7',
    produceType: 'derived',
    required: true,
    appliesTo: GOV,
    stubNote: '后期自动生成'
  },
  { code: '7.6', title: '培训教材', volumeId: '7', produceType: 'upload', required: true, appliesTo: GOV },
  { code: '7.7', title: '操作手册', volumeId: '7', produceType: 'upload', required: true, appliesTo: GOV },
  { code: '7.8', title: '维护手册', volumeId: '7', produceType: 'upload', required: true, appliesTo: GOV },
  { code: '7.9', title: '源代码及开发文档', volumeId: '7', produceType: 'upload', required: true, appliesTo: GOV },
  { code: '7.10', title: '竣工验收申请', volumeId: '7', produceType: 'upload', required: true, appliesTo: GOV },
  { code: '7.11', title: '竣工验收意见', volumeId: '7', produceType: 'upload', required: true, appliesTo: GOV }
]

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

export function isRequiredComplete(args: {
  required: boolean
  status: string
  generatedPath?: string | null
  uploadCount?: number
}): boolean {
  if (!args.required) return true
  if (args.status === 'confirmed' || args.status === 'waived') return true
  return false
}
