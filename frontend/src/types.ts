export interface CurrentUser {id:string;display_name:string;admin:boolean;bootstrap:boolean;company_ids:string[];write_company_ids:string[]}
export interface Company {archived?:boolean|null;archive_revision?:number;duplicate_rfc?:boolean;id:string;is_demo:boolean;name:string;rfc:string;person_type:'Moral'|'Física';trade_name:string;regime:string;accountant:string;email:string;phone:string;location:string;folder:string;notes:string;created_at:string}
export interface Task {id:string;company_id:string;title:string;category:string;responsible:string;due_date:string;priority:string;status:string;notes:string}
export interface Obligation {id:string;company_id:string;title:string;period:string;due_date:string;status:string;reference:string;notes:string}
export interface Document {id:string;company_id:string|null;name:string;category:string;size:number;created_at:string}
export interface Agent {id:string;online:boolean;capabilities:string[];last_seen:string}
export interface Job {id:string;company_id:string;agent_id:string;kind:string;status:string;result:{files?:{name:string;relative_path:string;extension:string;size:number}[];truncated?:boolean;error?:string;warnings?:string[]};created_at:string}
export interface State {archive_available?:boolean;current_user:CurrentUser;companies:Company[];tasks:Task[];obligations:Obligation[];documents:Document[];audit:{id:string;company_id:string;action:string;created_at:string}[];agents:Agent[];jobs:Job[];database:string;integrations:{sat:boolean;ocr:boolean;printing:boolean}}

export interface StorageCompany {id:string;name:string;rfc:string}
export interface StorageSource {id:string;label:string;kind:string;enabled:boolean;state:string;code:string|null}
export interface StorageOptions {companies:StorageCompany[];sources:StorageSource[];max_file_bytes:number;upload_formats:string[];identity_mode:string;can_review:boolean;can_write:boolean;write_company_ids:string[];can_index:boolean;can_classify:boolean}
export interface StorageLocation {source_id:string;label:string;kind:string;availability:string;last_seen_at:string|null;error_code:string|null}
export interface StorageDocument {id:string;name:string;size:number;revision:number;company_ids:string[];companies:StorageCompany[];document_type:string;category:string;period:string|null;classification_status:string;created_at:string;format:string;sources:StorageLocation[];availability:string}
export interface StoragePage {items:StorageDocument[];total:number;pending_count:number;offset:number;limit:number}
export interface StorageVersion {number:number;original_name:string;sha256:string|null;size:number;media_type:string;created_at:string}
export interface StorageDetail {document:StorageDocument;versions:StorageVersion[]}
