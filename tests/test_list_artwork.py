import copy,hashlib,io,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import list_artwork as a

def picture(size=(1920,1080),color='steelblue',comment=None):
    out=io.BytesIO();image=Image.new('RGB',size,color);opts={'comment':comment}if comment else{};image.save(out,format='JPEG',quality=93,**opts);return out.getvalue()
def source(season=1):return'https://www.apple.com/tv-pr/shows-and-films/e/example/images/season-%02d/key.medium.jpg'%season
def row(season=1):return{'url':'/tv-pr/originals/example/','title':'Example','showTypeKey':'series','image':{'dirpath':'/tv-pr/shows-and-films/e/example/images/season-%02d/thumbnail/key-art-01/'%season,'name':'Example_main_16_9.jpg','type':'jpg'}}
def html(season=1):
    path='/tv-pr/shows-and-films/e/example/images/season-%02d/show-home-graphic-header/key-art-01/16x9/Example_graphic.jpg'%season
    return('<source srcset="'+path+'.large.jpg 1x, '+path+'.large_2x.jpg 2x">').encode()
def item(art,season=1):return{'slug':'example','en':'Example','kind':'series','sourceArtwork':source(season),'artworkSeasonNumber':season,'artwork':art,'heroArtwork':art,'zh':{'detailMetadata':{'title':'已核验原子资料','rating':7.2}},'seasons':[{'season':season,'artwork':art}]}

class ListArtwork(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);(self.root/'docs/images').mkdir(parents=True);self.calls=[];self.page_calls=[]
        self.old=self.save(picture((472,266)));self.entry=item(self.old)
    def tearDown(self):self.temp.cleanup()
    def save(self,raw):
        ref='images/'+hashlib.sha256(raw).hexdigest()+'.jpg';(self.root/'docs'/ref).write_bytes(raw);return a.BASE+ref
    def fetch(self,url,deadline):self.calls.append(url);return picture()
    def page_fetch(self,url,deadline):self.page_calls.append(url);return html()
    def tiers(self,now=1_000_000,fetch=None):return a.Tiers(self.root,now,fetch or self.fetch,self.page_fetch)
    def test_real_threshold_keeps_628_and_large_originals(self):
        for size,expected in[((314,177),True),((334,188),True),((472,266),True),((628,354),False),((944,532),False),((960,540),False)]:
            self.assertEqual(a.small(self.root/'docs',item(self.save(picture(size)))),expected)
    def test_plan_is_offline_bounded_and_counts_due(self):
        other=copy.deepcopy(self.entry);other['slug']='second';other['sourceArtwork']=source().replace('/example/','/second/')
        tiers,selected,stats=a.plan({'entries':[self.entry,other]},self.root,1)
        self.assertEqual(stats['smallBelow600'],2);self.assertEqual(stats['due'],2);self.assertEqual(len(selected),1);self.assertEqual(self.calls,[]);self.assertFalse(tiers.path.exists())
    def test_same_work_type_and_depicted_season_only(self):
        self.assertIsNotNone(a.index_source(self.entry,row()))
        for changed in[dict(row(),title='Other'),dict(row(),showTypeKey='films'),row(2),dict(row(),url='/tv-pr/originals/other/')]:self.assertIsNone(a.index_source(self.entry,changed))
        bad=row();bad['image']['dirpath']='/tv-pr/shows-and-films/o/other/images/season-01/'
        self.assertIsNone(a.index_source(self.entry,bad))
    def test_real_pr_thumbnail_descriptor_uses_actual_header_srcset(self):
        entry={'slug':'prodigies','en':'Prodigies','kind':'series','artworkSeasonNumber':1,'sourceArtwork':'https://www.apple.com/tv-pr/shows-and-films/p/prodigies/images/season-01/thumbnail/key-art-01/Apple_TV_Prodigies_Key_Art_16_9_main_16_9.jpg'}
        descriptor={'url':'/tv-pr/originals/prodigies/','title':'Prodigies','showTypeKey':'series','image':{'dirpath':'/tv-pr/shows-and-films/p/prodigies/images/season-01/thumbnail/key-art-01/','name':'Apple_TV_Prodigies_Key_Art_16_9_main_16_9.jpg','type':'jpg'}}
        path='/tv-pr/shows-and-films/p/prodigies/images/season-01/show-home-graphic-header/key-art-01/16x9/Apple_TV_Prodigies_Key_Art_16_9_graphic_header_16_9_show_home.jpg'
        content='<source srcset="'+path+'.large.jpg 1x, '+path+'.large_2x.jpg 2x">'
        self.assertEqual(a.page_candidates(content,entry,a.index_source(entry,descriptor)),['https://www.apple.com'+path+'.large_2x.jpg','https://www.apple.com'+path+'.large.jpg'])
    def test_page_candidates_reject_other_work_season_role_and_keyart(self):
        content=html().decode();source=a.index_source(self.entry,row())
        self.assertEqual(len(a.page_candidates(content,self.entry,source)),2)
        for changed in[content.replace('/example/','/other/'),content.replace('/season-01/','/season-02/'),content.replace('/key-art-01/','/key-art-02/'),content.replace('/show-home-graphic-header/','/stills/'),content.replace('/16x9/','/2x3/')]:self.assertEqual(a.page_candidates(changed,self.entry,source),[])
    def test_legacy_key_art_srcset_and_commas_do_not_require_header_layout(self):
        content=html().decode().replace('/show-home-graphic-header/','/').replace('/16x9/','/').replace(' 1x, ', ', ')
        urls=a.page_candidates(content,self.entry,a.index_source(self.entry,row()))
        self.assertEqual(len(urls),2);self.assertTrue(urls[0].endswith('.large_2x.jpg'));self.assertTrue(urls[1].endswith('.large.jpg'))
        self.assertEqual(a.page_candidates(content.replace('_graphic.jpg','_graphic_4_1.jpg'),self.entry,a.index_source(self.entry,row())),[])
    def season_row(self,art,number=1,show='umc.cmc.show'):
        return{'season':number,'metadataStatus':'verified','showId':show,'officialId':'umc.cmc.season'+str(number),'artwork':art,'sourceArtwork':'https://is1-ssl.mzstatic.com/image/season'+str(number)+'/960x540.jpg'}
    def test_verified_exact_season_bytes_are_reused_without_network(self):
        art=self.save(picture());self.entry['officialIdentity']={'watchUrl':'https://tv.apple.com/us/show/example/umc.cmc.show'};self.entry['seasons']=[self.season_row(art)];before=copy.deepcopy(self.entry)
        tiers=self.tiers();out=tiers.upgrade(self.entry,None)
        self.assertEqual(out['status'],'upgraded');self.assertEqual(out['attempts'],0);self.assertEqual(out['sourceRole'],'verified-season-cache');self.assertEqual(self.calls,[]);self.assertEqual(self.page_calls,[])
        self.assertTrue(tiers.apply(self.entry));self.assertEqual(self.entry['seasons'],before['seasons']);self.assertEqual(self.entry['zh'],before['zh']);self.assertEqual(self.entry['heroArtwork'],before['heroArtwork'])
    def test_cached_series_cannot_borrow_other_season_show_or_pending_art(self):
        art=self.save(picture());self.entry['officialIdentity']={'watchUrl':'https://tv.apple.com/us/show/example/umc.cmc.show'}
        for row in[self.season_row(art,2),self.season_row(art,show='umc.cmc.other'),dict(self.season_row(art),metadataStatus='pending'),dict(self.season_row(art),sourceArtwork='https://untrusted.test/image.jpg')]:
            self.entry['seasons']=[row];self.assertIsNone(a.cached_original(self.root/'docs',self.entry))
    def test_home_season_cache_requires_same_work_identity(self):
        art=self.save(picture());watch='https://tv.apple.com/us/show/example/umc.cmc.show';self.entry['officialIdentity']={'watchUrl':watch}
        work={'slug':'example','kind':'series','officialId':'umc.cmc.show','watchUrl':watch,'seasons':[self.season_row(art)]}
        self.assertIsNotNone(a.cached_original(self.root/'docs',self.entry,{'works':[work]}))
        self.assertIsNone(a.cached_original(self.root/'docs',self.entry,{'works':[dict(work,officialId='umc.cmc.other')]}))
    def test_movie_uses_only_its_own_verified_large_hero(self):
        entry=copy.deepcopy(self.entry);entry.update(kind='movie',heroArtwork=self.save(picture()),heroSource='https://is1-ssl.mzstatic.com/image/movie/1280x960sr.jpg',officialIdentity={'watchUrl':'https://tv.apple.com/us/movie/example/umc.cmc.movie'})
        self.assertIsNotNone(a.cached_original(self.root/'docs',entry));entry['heroSource']='https://untrusted.test/movie.jpg';self.assertIsNone(a.cached_original(self.root/'docs',entry))
    def test_same_movie_home_hero_reuse_checks_id_medium_and_dimensions(self):
        art=self.save(picture());watch='https://tv.apple.com/us/movie/example/umc.cmc.movie';entry=copy.deepcopy(self.entry);entry.update(kind='movie',officialIdentity={'watchUrl':watch})
        work={'slug':'example','kind':'movie','officialId':'umc.cmc.movie','watchUrl':watch};ref={'slug':'example','officialId':'umc.cmc.movie','artwork':art,'width':1920,'height':1080};home={'source':'https://tv.apple.com/us/channel/apple-tv/tvs.sbd.4000','works':[work],'hero':[ref]}
        self.assertEqual(a.cached_original(self.root/'docs',entry,home)[2],'verified-movie-home-cache')
        for changed in[dict(ref,officialId='umc.cmc.other'),dict(ref,width=1280,height=720)]:self.assertIsNone(a.cached_original(self.root/'docs',entry,dict(home,hero=[changed])))
        self.assertIsNone(a.cached_original(self.root/'docs',entry,dict(home,works=[dict(work,kind='series')])) )
        entry['kind']='series';self.assertIsNone(a.cached_original(self.root/'docs',entry,home))
    def test_source_normalization_is_independent_of_text_metadata(self):
        self.assertEqual(a.source_key(source(),self.entry),a.source_key(source().replace('.medium.','.large_2x.'),self.entry))
        other=copy.deepcopy(self.entry);other['zh']={'title':'新中文片名','detailMetadata':{'rating':8.0}}
        self.assertEqual(a.source_key(source(),self.entry),a.source_key(source(),other))
        self.assertNotEqual(a.source_key(source(),self.entry),a.source_key(source(2),item(self.old,2)))
        self.assertIsNone(a.source_key(source().replace('/example/','/other/'),self.entry))
    def test_rejects_untrusted_or_ambiguous_urls(self):
        for url in['http://www.apple.com/tv-pr/shows-and-films/e/example/images/x.jpg','https://www.apple.com.evil.test/tv-pr/shows-and-films/e/example/images/x.jpg',source()+'?token=private',source().replace('www.apple.com','secret@www.apple.com'),source().replace('/images/','/images/../'),source().replace('/images/','/images/%2e%2e/')]:self.assertIsNone(a.canonical(url))
    def test_derivative_is_real_640_srgb_jpeg_without_upscaling(self):
        raw=a.derivative(picture());
        with Image.open(io.BytesIO(raw))as image:self.assertEqual(image.size,(640,360));self.assertEqual(image.mode,'RGB');self.assertEqual(image.format,'JPEG')
        for size in[(472,266),(1080,1920),(1200,900),(8192,4608)]:
            with self.assertRaises(ValueError):a.derivative(picture(size))
    def test_failure_keeps_original_and_has_at_most_two_attempts(self):
        before=copy.deepcopy(self.entry)
        def broken(url,deadline):self.calls.append(url);raise OSError('unavailable')
        tiers=self.tiers(fetch=broken);out=tiers.upgrade(self.entry,row())
        self.assertEqual(out['status'],'retained');self.assertEqual(out['attempts'],2);self.assertEqual(self.entry,before);self.assertFalse(tiers.apply(self.entry));self.assertFalse(tiers.needs(self.entry));self.assertEqual(len(self.calls),2)
    def test_cached_packet_reuses_bytes_without_touching_hero_or_chinese(self):
        before=copy.deepcopy(self.entry);tiers=self.tiers();self.assertEqual(tiers.upgrade(self.entry,row())['status'],'upgraded');self.assertEqual(self.entry,before)
        self.assertTrue(tiers.apply(self.entry));self.assertEqual(a.dimensions(self.root/'docs',self.entry['artwork']),(640,360));self.assertEqual(self.entry['heroArtwork'],before['heroArtwork']);self.assertEqual(self.entry['zh'],before['zh']);self.assertEqual(self.entry['seasons'],before['seasons'])
        again=self.tiers(now=1_000_010);self.assertFalse(again.needs(self.entry));changed=copy.deepcopy(before);changed['zh']['newName']='只更新资料';self.assertTrue(again.apply(changed));self.assertEqual(changed['artwork'],self.entry['artwork']);self.assertEqual(len(self.calls),1)
    def test_expired_tier_is_rechecked_but_kept_on_failure(self):
        tiers=self.tiers();tiers.upgrade(self.entry,row());tiers.apply(self.entry)
        later=self.tiers(now=1_000_000+a.TTL+1);self.assertTrue(later.needs(self.entry));self.assertTrue(later.apply(self.entry))
    def test_expired_managed_640_can_refresh_without_downgrading_native_640(self):
        tiers=self.tiers();tiers.upgrade(self.entry,row());tiers.apply(self.entry);old=self.entry['artwork']
        later=self.tiers(now=1_000_000+a.TTL+1,fetch=lambda url,deadline:picture(color='red'))
        self.assertEqual(later.upgrade(self.entry,row())['status'],'upgraded');self.assertTrue(later.apply(self.entry));self.assertNotEqual(self.entry['artwork'],old)
        native=self.save(picture((640,360),color='green'));self.entry['artwork']=native;self.assertFalse(later.apply(self.entry));self.assertEqual(self.entry['artwork'],native)
    def test_failed_first_rows_cannot_starve_untried_rows(self):
        tiers=self.tiers(fetch=lambda url,deadline:(_ for _ in()).throw(OSError('failed')));tiers.upgrade(self.entry,row())
        second=copy.deepcopy(self.entry);second['slug']='second';second['sourceArtwork']=source().replace('/example/','/second/')
        unsupported=copy.deepcopy(self.entry);unsupported['slug']='unsupported';unsupported['sourceArtwork']='https://untrusted.test/image.jpg'
        _,selected,stats=a.plan({'entries':[self.entry,unsupported,second]},self.root,1)
        self.assertEqual(selected[0]['slug'],'second');self.assertEqual(stats['due'],2);self.assertEqual(stats['unsupported'],['unsupported'])
    def test_retry_failed_does_not_redownload_fresh_successes(self):
        tiers=self.tiers(now=int(a.time.time()));tiers.upgrade(self.entry,row())
        second=copy.deepcopy(self.entry);second['slug']='second';second['sourceArtwork']=source().replace('/example/','/second/');key=a.source_key(second['sourceArtwork'],second);tiers.cache['failures'][key]={'checkedAt':int(a.time.time()),'reason':'no_source'};tiers.save()
        _,selected,_=a.plan({'entries':[self.entry,second]},self.root,122,retry_failed=True)
        self.assertEqual([e['slug']for e in selected],['second'])
    def test_later_large_original_is_never_downgraded_by_old_cache(self):
        tiers=self.tiers();tiers.upgrade(self.entry,row());large=self.save(picture((944,532)));self.entry['artwork']=large
        self.assertFalse(tiers.apply(self.entry));self.assertEqual(self.entry['artwork'],large);self.assertFalse(tiers.needs(self.entry))
    def test_corrupt_cached_file_or_wrong_season_cannot_activate(self):
        tiers=self.tiers();tiers.upgrade(self.entry,row());cached=tiers.cached(self.entry);a.local_path(self.root/'docs',cached['artwork']).write_bytes(b'bad')
        self.assertIsNone(tiers.cached(self.entry));self.assertFalse(tiers.apply(self.entry));self.assertIsNone(tiers.cached(item(self.old,2)))
    def test_upstream_jpeg_metadata_does_not_change_derivative_pixels_or_bytes(self):
        raw=picture();with_comment=raw[:2]+b'\xff\xfe\x00\x06test'+raw[2:]
        self.assertEqual(a.derivative(raw),a.derivative(with_comment))
    def test_stream_size_and_redirect_are_bounded_before_decode(self):
        class Reply:
            status_code=200
            headers={}
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def raise_for_status(self):pass
            def iter_content(self,n):return iter([b'x'*(a.MAX_BYTES+1)])
        with patch.object(a.requests,'get',return_value=Reply())as fetch:
            with self.assertRaises(ValueError):a.download(source(),a.time.monotonic()+10)
            self.assertFalse(fetch.call_args.kwargs['allow_redirects']);self.assertTrue(fetch.call_args.kwargs['stream'])
        response=Reply();response.status_code=302
        with patch.object(a.requests,'get',return_value=response):
            with self.assertRaises(ValueError):a.download(source(),a.time.monotonic()+10)
        response=Reply();response.headers={'Content-Length':str(a.MAX_BYTES+1)}
        with patch.object(a.requests,'get',return_value=response):
            with self.assertRaises(ValueError):a.download(source(),a.time.monotonic()+10)

if __name__=='__main__':unittest.main()
