/* Generated from FastAPI OpenAPI. Run `python tools/generate_api_types.py` to refresh. */

export type ApiError = {
  code: string;
  message: string;
  nextAction: string;
  details?: unknown;
  [key: string]: unknown;
};

export type ApiErrorOut = {
  error: ApiError;
  [key: string]: unknown;
};

export type AppConfigOut = {
  brandName?: null | string;
  heroTitle?: null | string;
  heroSubtitle?: null | string;
  brandFontSize?: null | string;
  brandColor?: null | string;
  titleFontSize?: null | string;
  titleColor?: null | string;
  subtitleFontSize?: null | string;
  subtitleColor?: null | string;
  layout?: null | string;
  navPosition?: null | string;
  detailPosition?: null | string;
  favoritesSort?: Array<{
  [key: string]: unknown;
}>;
  sidebarSort?: null | string;
  media?: {
  [key: string]: unknown;
};
  [key: string]: unknown;
};

export type AppConfigUpdateIn = {
  brandName?: null | string;
  heroTitle?: null | string;
  heroSubtitle?: null | string;
  brandFontSize?: null | string;
  brandColor?: null | string;
  titleFontSize?: null | string;
  titleColor?: null | string;
  subtitleFontSize?: null | string;
  subtitleColor?: null | string;
  layout?: null | string;
  navPosition?: null | string;
  detailPosition?: null | string;
  favoritesSort?: Array<SortLevel> | null;
  sidebarSort?: null | string;
  media?: MediaConfigIn | null;
  [key: string]: unknown;
};

export type AttachmentIn = {
  id?: null | number;
  name: string;
  filename: string;
  mimeType?: null | string;
  thumbFilename?: null | string;
  originalFilename?: null | string;
  width?: null | number;
  height?: null | number;
  bytes?: null | number;
};

export type AttachmentOut = {
  id?: null | number;
  name: string;
  filename: string;
  thumbFilename?: null | string;
  originalFilename?: null | string;
  mimeType?: null | string;
  width?: null | number;
  height?: null | number;
  bytes?: null | number;
  url: string;
  thumbUrl?: null | string;
  originalUrl?: null | string;
  imageUrl?: null | string;
  [key: string]: unknown;
};

export type Body_media_upload = {
  file: string;
};

export type Body_topics_import = {
  file: string;
};

export type BookshelfCreateIn = {
  name: string;
  title?: null | string;
};

export type BookshelfOut = {
  id?: null | number;
  name: string;
  title: string;
  createdAt?: null | string;
  updatedAt?: null | string;
  topicCount?: number;
  noteCount?: number;
  [key: string]: unknown;
};

export type BookshelfTopicEntry = {
  topic: TopicOut;
  eras?: Array<EraCount>;
  [key: string]: unknown;
};

export type BookshelfTreeItem = {
  id?: null | number;
  name: string;
  title: string;
  createdAt?: null | string;
  updatedAt?: null | string;
  topicCount?: number;
  noteCount?: number;
  topics?: Array<BookshelfTopicEntry>;
  [key: string]: unknown;
};

export type BookshelfUpdateIn = {
  name?: null | string;
  title?: null | string;
};

export type BoundsOut = {
  noteCount?: number;
  minDateKey?: null | number;
  maxDateKey?: null | number;
  minDate?: null | string;
  maxDate?: null | string;
  hasImage?: boolean | null;
  supportedZoomLevels?: Array<unknown>;
  [key: string]: unknown;
};

export type ColumnDef = {
  key: string;
  label: string;
  type?: string;
  width?: number;
  order?: number;
  visible?: boolean;
  options?: Array<OptionDef>;
};

export type DeleteOut = {
  ok: boolean;
  deletedAt?: null | string;
  updatedAt?: null | string;
  [key: string]: unknown;
};

export type EraCount = {
  era: string;
  count: number;
  [key: string]: unknown;
};

export type FeatureMapOut = {
  version: string;
  features: Array<FeatureOut>;
  [key: string]: unknown;
};

export type FeatureOperationOut = {
  operationId: string;
  method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  path: string;
  readOnly?: boolean;
  lifecycle?: 'active' | 'compatibility' | 'deprecated';
  clientMethod?: null | string;
  cliCommand?: null | string;
  requestSchema?: null | string;
  querySchema?: null | string;
  responseSchema?: null | string;
  requestHeaders?: Array<string>;
  contentType?: string;
  [key: string]: unknown;
};

export type FeatureOut = {
  id: string;
  title: string;
  summary: string;
  ui: FeatureUiOut;
  api: Array<FeatureOperationOut>;
  stateOwner: string;
  dataScope: string;
  preconditions: Array<string>;
  permissions: Array<string>;
  persistedResult: string;
  failureRecovery: Array<string>;
  operationIdentity?: null | string;
  scenarios: Array<FeatureScenarioOut>;
  [key: string]: unknown;
};

export type FeatureScenarioOut = {
  id: string;
  title: string;
  summary: string;
  inputSchema: string;
  readOnly?: boolean;
  preconditions?: Array<string>;
  steps?: Array<FeatureScenarioStepOut>;
  cleanup?: string;
  [key: string]: unknown;
};

export type FeatureScenarioStepOut = {
  id: string;
  operationId: string;
  assertions?: Array<string>;
  persistence?: string;
  [key: string]: unknown;
};

export type FeatureUiOut = {
  route?: null | string;
  entryPoint: string;
  hasWebEntry?: boolean;
  contractIds?: Array<string>;
  [key: string]: unknown;
};

export type HTTPValidationError = {
  detail?: Array<ValidationError>;
};

export type ImageUploadOut = {
  id: number;
  filename: string;
  originalName: string;
  mimeType?: null | string;
  url: string;
  imageUrl?: null | string;
  [key: string]: unknown;
};

export type ImportOut = {
  ok: boolean;
  count: number;
  [key: string]: unknown;
};

export type MediaConfigIn = {
  compress?: boolean | null;
  keepOriginal?: boolean | null;
  quality?: null | number;
  maxEdge?: null | number;
  thumbEdge?: null | number;
};

export type NoteDateParts = {
  year?: null | number;
  month?: null | number;
  day?: null | number;
  [key: string]: unknown;
};

export type NoteIndexItem = {
  id: number;
  topicId: number;
  hasDate: boolean;
  dateKey?: null | number;
  isoDate?: null | string;
  dateParts: NoteDateParts;
  displayLabel: string;
  headline: string;
  era: string;
  image?: null | string;
  imageUrl?: null | string;
  thumbUrl?: null | string;
  extra?: {
  [key: string]: unknown;
};
  favorite?: boolean;
  favoriteAt?: null | string;
  deletedAt?: null | string;
  createdAt: string;
  updatedAt: string;
  preview?: string;
  searchText?: string;
  attachmentCount?: number;
  [key: string]: unknown;
};

export type NoteIndexOut = {
  topics: Array<TopicOut>;
  notes: Array<NoteIndexItem>;
  [key: string]: unknown;
};

export type NoteItemIn = {
  tag?: string;
  text: string;
};

export type NoteItemOut = {
  tag: string;
  text: string;
  [key: string]: unknown;
};

export type NoteListItem = {
  id: number;
  topicId: number;
  nodeType?: string;
  hasDate: boolean;
  dateKey?: null | number;
  isoDate?: null | string;
  dateParts: NoteDateParts;
  displayLabel: string;
  sortKey: number;
  headline: string;
  legacyYear: string;
  era: string;
  image?: null | string;
  imageUrl?: null | string;
  thumbUrl?: null | string;
  extra?: {
  [key: string]: unknown;
};
  favorite?: boolean;
  favoriteAt?: null | string;
  deletedAt?: null | string;
  createdAt: string;
  updatedAt: string;
  preview?: string;
  searchText?: string;
  attachmentCount?: number;
  [key: string]: unknown;
};

export type NoteOut = {
  id: number;
  topicId: number;
  nodeType?: string;
  hasDate: boolean;
  dateKey?: null | number;
  isoDate?: null | string;
  dateParts: NoteDateParts;
  displayLabel: string;
  sortKey: number;
  headline: string;
  legacyYear: string;
  era: string;
  image?: null | string;
  imageUrl?: null | string;
  thumbUrl?: null | string;
  bodyMarkdown?: string;
  extra?: {
  [key: string]: unknown;
};
  attachments?: Array<AttachmentOut>;
  createdAt: string;
  updatedAt: string;
  favorite?: boolean;
  favoriteAt?: null | string;
  deletedAt?: null | string;
  items?: Array<NoteItemOut>;
  [key: string]: unknown;
};

export type NotePageOut = {
  items: Array<NoteListItem>;
  bounds: BoundsOut;
  range: NoteRangeOut;
  hasMore: boolean;
  nextCursor?: null | string;
  [key: string]: unknown;
};

export type NoteRangeOut = {
  from?: null | number;
  to?: null | number;
  cursor?: null | number;
  limit?: null | number;
  [key: string]: unknown;
};

export type NoteSearchItem = {
  id: number;
  topicId: number;
  headline: string;
  snippet: string;
  dateKey?: null | number;
  isoDate?: null | string;
  rank: number;
  [key: string]: unknown;
};

export type NoteStatePatchIn = {
  favorite?: boolean | null;
  deletedAt?: null | string;
};

export type NoteWriteIn = {
  id?: null | number;
  dateYear?: null | number;
  dateMonth?: null | number;
  dateDay?: null | number;
  headline: string;
  era?: string;
  bodyMarkdown?: string;
  attachments?: Array<AttachmentIn>;
  extra?: {
  [key: string]: unknown;
};
  items?: Array<NoteItemIn>;
  image?: null | string;
  favorite?: boolean | null;
  deletedAt?: null | string;
};

export type OkOut = {
  ok: boolean;
  [key: string]: unknown;
};

export type OptionDef = {
  id: string;
  label?: string;
  color?: string;
};

export type RuntimeIdentityOut = {
  databaseIdentity: string;
  [key: string]: unknown;
};

export type SortLevel = {
  field: string;
  dir: number;
};

export type SummaryItemOut = {
  id: string;
  nodeType: string;
  groupBy: string;
  bucketKey: number;
  displayLabel: string;
  headline: string;
  sortKey: number;
  dateKey: number;
  rangeStartKey: number;
  rangeEndKey: number;
  rangeStartDate: string;
  rangeEndDate: string;
  noteCount: number;
  era: string;
  image?: null | string;
  items?: Array<NoteItemOut>;
  [key: string]: unknown;
};

export type SummaryRangeOut = {
  from?: null | number;
  to?: null | number;
  [key: string]: unknown;
};

export type TopicCreateIn = {
  name: string;
  bookshelfId?: null | number;
};

export type TopicExportOut = {
  schemaVersion: number;
  title: string;
  subtitle: string;
  columns: Array<{
  [key: string]: unknown;
}>;
  notes: Array<NoteOut>;
  [key: string]: unknown;
};

export type TopicMetaUpdateIn = {
  title?: null | string;
  subtitle?: null | string;
  bookshelfId?: null | number;
  displayStyle?: null | string;
  containerType?: null | string;
  sort?: Array<SortLevel> | null;
  groupBy?: null | string;
  columns?: Array<ColumnDef> | null;
};

export type TopicOut = {
  id: number;
  name: string;
  title: string;
  subtitle: string;
  bookshelfId?: null | number;
  bookshelfName?: null | string;
  bookshelfTitle?: null | string;
  columns?: Array<{
  [key: string]: unknown;
}>;
  displayStyle?: string;
  containerType?: string;
  views?: Array<string>;
  defaultView?: null | string;
  sort?: Array<{
  [key: string]: unknown;
}>;
  groupBy?: string;
  capabilities?: Array<string>;
  capabilitySignals?: null | {
  [key: string]: unknown;
};
  updatedAt?: null | string;
  noteCount?: null | number;
  minDateKey?: null | number;
  maxDateKey?: null | number;
  minDate?: null | string;
  maxDate?: null | string;
  [key: string]: unknown;
};

export type TopicSummaryOut = {
  items: Array<SummaryItemOut>;
  bounds: BoundsOut;
  groupBy: string;
  range: SummaryRangeOut;
  [key: string]: unknown;
};

export type ValidationError = {
  loc: Array<number | string>;
  msg: string;
  type: string;
  input?: unknown;
  ctx?: Record<string, unknown>;
};

export type NotesListParams = {
  "from"?: null | string;
  "to"?: null | string;
  "cursor"?: null | string;
  "limit"?: number;
  "dir"?: number;
};

export type NotesSearchParams = {
  "q"?: string;
  "limit"?: number;
};

export type TopicSummaryParams = {
  "groupBy": 'year' | 'month';
  "from"?: null | string;
  "to"?: null | string;
};

export type TopicExportParams = {
  "from"?: null | string;
  "to"?: null | string;
};

export type ApiOperationId = 'bookshelves_create' | 'bookshelves_delete' | 'bookshelves_list' | 'bookshelves_tree' | 'bookshelves_update' | 'config_get' | 'config_update' | 'features_get' | 'features_list' | 'images_images__filename__get' | 'media_delete' | 'media_read' | 'media_upload' | 'notes_create' | 'notes_delete' | 'notes_get' | 'notes_index' | 'notes_list' | 'notes_search' | 'notes_update' | 'runtime_identity' | 'serve_frontend__full_path__get' | 'serve_frontend_index__get' | 'themes_list' | 'themes_vars_get' | 'themes_vars_update' | 'topics_create' | 'topics_delete' | 'topics_export' | 'topics_get' | 'topics_import' | 'topics_list' | 'topics_meta_get' | 'topics_meta_update' | 'topics_summary';
