"""Scoped monitoring of public certificates. Date checks are not SAT/chain/revocation validation."""
import math
from sqlalchemy import select, func, update
from cryptography import x509
from cryptography.x509.oid import NameOID
from ..models import Company, Document, DocumentCompanyLink, now
from .classifier import RFC, valid_rfc
from .providers import StorageError

USAGES={'e.firma (FIEL)':'fiel','CSD':'csd'}


def certificate_metadata(stream,stamp):
    data=stream.read()
    cert=x509.load_pem_x509_certificate(data) if data.lstrip().startswith(b'-----BEGIN') else x509.load_der_x509_certificate(data)
    rfcs=sorted({r for attr in cert.subject for r in RFC.findall(str(attr.value).upper()) if valid_rfc(r)})
    start,end=cert.not_valid_before_utc,cert.not_valid_after_utc
    days=math.ceil((end-stamp).total_seconds()/86400)
    state='not_yet_valid' if stamp<start else 'expired' if stamp>end else 'expiring' if days<=30 else 'valid'
    names=cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    return {'rfcs':rfcs,'holder':str(names[0].value)[:200] if names else '',
            'valid_from':start,'valid_until':end,'days_remaining':days,'temporal_state':state,
            'serial':format(cert.serial_number,'X')}


class DashboardService:
    def __init__(self,service):
        self.service=service

    def report(self,actor,company_id=None):
        actor.require('read',company_id)
        service=self.service
        stamp=now()
        with service.sessions() as db:
            companies=db.scalars(select(Company).where(True if actor.admin else Company.id.in_(actor.company_ids),
                True if company_id is None else Company.id==company_id).order_by(Company.name)).all()
            company_data={c.id:{'id':c.id,'name':c.name,'rfc':c.rfc,'fiel_state':'missing','certificate_id':None,
                                'valid_until':None,'document_count':0} for c in companies}
            direct=select(Document.id.label('document_id'),Document.company_id.label('company_id')).where(
                service._scope(actor),Document.company_id.in_(company_data))
            linked=select(Document.id.label('document_id'),DocumentCompanyLink.company_id.label('company_id')).join(
                DocumentCompanyLink,DocumentCompanyLink.document_id==Document.id).where(
                service._scope(actor),DocumentCompanyLink.company_id.in_(company_data))
            associations=direct.union(linked).subquery()
            for cid,count in db.execute(select(associations.c.company_id,func.count()).group_by(associations.c.company_id)):
                company_data[cid]['document_count']=count
            cert_docs=db.scalars(select(Document).where(service._scope(actor),func.lower(Document.name).like('%.cer'),
                Document.id.in_(select(associations.c.document_id))).order_by(Document.created_at.desc(),Document.id).limit(201)).all()
            links={d.id:service._companies(db,d)&company_data.keys() for d in cert_docs}
            truncated=len(cert_docs)>200
            cert_docs=cert_docs[:200]
        certificates=[]
        priorities={'valid':5,'expiring':4,'not_yet_valid':3,'expired':2,'rfc_mismatch':1,'unverified':1,'unavailable':0}
        for doc in cert_docs:
            item={'id':doc.id,'name':doc.name,'revision':doc.storage_revision,'usage':USAGES.get(doc.category,'unknown'),
                  'company_ids':sorted(links[doc.id]),'state':'unavailable','rfcs':[],
                  'valid_from':None,'valid_until':None,'days_remaining':None,'serial':None,'holder':'','code':None}
            try:
                service.verify_legacy(actor,doc.id)
                with service.read(actor,doc.id) as content:
                    item.update(certificate_metadata(content.stream,stamp))
                    item['revision']=content.document.revision
                item['state']=item['temporal_state']
            except StorageError as exc:
                item['code']=exc.code
            except (ValueError,TypeError):
                item['code']='invalid_public_certificate'
            certificates.append(item)
            if item['usage']!='fiel':
                continue
            for cid in links[doc.id]:
                company=company_data[cid]
                state=item['state']
                if state!='unavailable':
                    if doc.classification_status!='confirmed' or not item['rfcs']:
                        state='unverified'
                    elif company['rfc'].upper() not in item['rfcs']:
                        state='rfc_mismatch'
                previous=company['fiel_state']
                if previous=='missing' or priorities[state]>priorities.get(previous,-1) or (
                    priorities[state]==priorities.get(previous,-1) and item['valid_until'] and
                    (company['valid_until'] is None or item['valid_until']>company['valid_until'])):
                    company.update(fiel_state=state,certificate_id=doc.id,valid_until=item['valid_until'])
        if truncated:
            for company in company_data.values():
                if company['fiel_state'] not in {'valid','expiring'}:
                    company['fiel_state']='unverified'
        counts={state:sum(c['fiel_state']==state for c in company_data.values()) for state in ['valid','expiring','expired','missing','not_yet_valid','unverified','rfc_mismatch','unavailable']}
        return {'checked_at':stamp,'companies':list(company_data.values()),'certificates':certificates,'counts':counts,
                'truncated':truncated,'sat_validated':False,'max_certificates':200}

    def label(self,actor,ident,revision,usage):
        if usage not in {'fiel','csd','unknown'}:
            raise StorageError('invalid_metadata')
        service=self.service
        with service.sessions.begin() as db:
            doc=service._document(db,actor,ident,'write')
            if not doc.name.lower().endswith('.cer'):
                raise StorageError('invalid_public_certificate')
            category={'fiel':'e.firma (FIEL)','csd':'CSD','unknown':'Certificado público'}[usage]
            changed=db.execute(update(Document).where(Document.id==ident,Document.storage_revision==revision)
                               .values(category=category,document_type='certificate'))
            if not changed.rowcount:
                raise StorageError('revision_conflict')
            service._event(db,actor,'certificate_usage_declared',document_id=ident)
        return {'ok':True}
