/** Original ContaSuite 0.6 assets, copied byte-for-byte from the supplied package. */
export const originalIcons={suite:'CS_ContaSuite',recopilador:'CR_Recopila',cfdi:'CF_CFDI',recibos:'CG_Recibos',declaraciones:'CD_Declara'} as const;
export type OriginalIconName=keyof typeof originalIcons;
export const moduleIconNames:Record<string,OriginalIconName>={'recopilador-cfdi':'recopilador','organizador-cfdi':'cfdi',recibos:'recibos',declara:'declaraciones'};
export function OriginalIcon({name,size=28,sidebar=false,label}:{name:OriginalIconName;size?:number;sidebar?:boolean;label?:string}){
 const resolution=size>64?192:size>32?128:64;
 const file=originalIcons[name];
 return <span className={'original-icon'+(sidebar?' on-sidebar':'')} style={{width:size,height:size}} role={label?'img':undefined} aria-label={label} aria-hidden={label?undefined:true}><img className="original-light" src={`/icons/original/claro/${resolution}/${file}.png`} alt="" width={size} height={size}/><img className="original-dark" src={`/icons/original/oscuro/${resolution}/${file}.png`} alt="" width={size} height={size}/></span>
}
