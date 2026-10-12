"""Independent synthetic acceptance for the 68 adopted H05 identifiers.

Expected populations/labels/history below are hand specified. Negative cases
alter inputs or packaged bytes; PASS records are written after the assertion,
never copied from the contract's definition list or producer's PASS labels.
"""
from collections import Counter
from copy import deepcopy
import csv
import json
import math
from pathlib import Path
import re
import shutil
import tempfile
import unittest

import config
from src import steam_handoff as h

H05_RESULTS = {}


def row(key, year, **changes):
    value=dict(appid=key,name='Synthetic; "quoted",\nrecord',release_date=f'{year}-01-01',
        english='1',required_age='0',developer='A',publisher='P',platforms='windows;mac',
        categories='Action',genres='Indie',positive_ratings='10',negative_ratings='0')
    value.update(changes)
    return value


def fixture():
    main=[row(' 001 ',1997,positive_ratings='1'),row('12',2016,developer='A;B;A',positive_ratings='5'),
        row('13',2016,positive_ratings='15'),
        row('14',2017,developer='A;B;A',platforms=';;',categories=' unknown ',positive_ratings='2'),
        row('15',2017,developer='',publisher='   ',platforms=' UNKNOWN ',english='',required_age='nan',positive_ratings='50'),
        row('16',2018,platforms='Windows;windows;notwindows',genres='Action,Indie',positive_ratings='7'),
        row('17',2019,positive_ratings='bad'),row('18',2020,positive_ratings='9'),
        row('19',2018,release_date='bad-date',positive_ratings='bad')]
    aux={name:[{('appid' if name=='steamspy_tag_data.csv' else 'steam_appid'):'001'},
               {('appid' if name=='steamspy_tag_data.csv' else 'steam_appid'):'12'}]
         for name in h.SOURCE_NAMES[1:]}
    aux['steam_description_data.csv'].append(dict(steam_appid='999'))
    aux['steam_support_info.csv']=[]
    return main,aux


def _virtual_marker(directory):
    return dict(manifest_sha256=h.file_hash(directory/'manifest/manifest.json'),
                report_sha256=h.file_hash(directory/'manifest/validation_report.json'))


class HandoffAssertions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='steam-v12-h05-')
        cls.main,cls.aux=fixture();cls.data=h.build_dataset(cls.main,cls.aux)
        cls.package=h.write_package(cls.data,cls.temp.name,scope='synthetic',issue_ready=True)
        cls.directory=cls.package['directory'];cls.manifest=cls.package['manifest'];cls.report=cls.package['report']
        if cls.report['overall']!='pass':raise AssertionError(cls.report)
        cls.x={r['appid']:r for r in cls.data.tables['handoff/x_primary.csv']}
        cls.y={r['appid']:r for r in cls.data.tables['handoff/y_label.csv']}
        cls.meta={r['raw_appid'].strip():r for r in cls.data.tables['handoff/keys_meta.csv']}
        cls.cut={r['release_year']:r for r in cls.data.tables['handoff/year_cutoffs.csv']}
        cls.edges=cls.data.tables['handoff/history_source_membership.csv']
        cls.schema,cls.definitions=h._load_spec()

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def record(self,identifier,evidence):
        self.assertNotIn(identifier,H05_RESULTS)
        H05_RESULTS[identifier]=dict(status='PASS',scope='synthetic',evidence=dict(test_method=self._testMethodName,observations=evidence))

    def case(self,identifier):
        """Each branch executes its own assertions against actual synthetic results."""
        p=identifier.rsplit('-',1)[0];n=int(identifier.rsplit('-',1)[1]);evidence={}
        if p=='H05-KEY':
            if n==1:
                for path,rows in self.data.tables.items():
                    pk=self.schema['files'][path]['primary_key'];self.assertEqual(len(rows),len({tuple(r[k] for k in pk) for r in rows}))
                windows=self.data.history_windows['target_windows'];self.assertEqual(len(windows),len({(r['window_variant'],r['target_appid'],r['entity_kind']) for r in windows}));evidence={'relation_keys_unique':True,'window_records':len(windows)}
            elif n==2:
                collision=h.build_dataset([row(' 12 ',2016),row('12',2016)]);self.assertEqual(collision.key_audits['steam.csv']['strip_collision_count'],1);self.assertEqual(len(collision.tables['handoff/rows_invalid_unknown.csv']),2)
                keep=h.build_dataset([row('0012',2016),row('12',2016)]);self.assertEqual({r['appid'] for r in keep.tables['handoff/x_primary.csv']},{'0012','12'});evidence={'strip_collision_blocks':2,'zero_prefix_keys_distinct':True}
            elif n==3:
                expected={('steam.csv',i) for i in range(1,10)}
                for path in ['handoff/keys_meta.csv','handoff/row_disposition.csv']:self.assertEqual({(r['source_file'],r['source_row_no']) for r in self.data.tables[path]},expected)
                evidence={'record_identities':9}
            elif n==4:
                self.assertEqual(self.data.statistics['dispositions'],{'train':3,'validation':2,'test':1,'excluded_2019':1,'uncovered_year':1,'invalid_date_nat':1});self.assertEqual(sum(self.data.statistics['dispositions'].values()),9);evidence=self.data.statistics['dispositions']
            elif n==5:
                bad=h.build_dataset([row('+1',2019,release_date='bad-date')]);r=bad.tables['handoff/row_disposition.csv'][0];self.assertEqual(r['disposition'],'invalid_key');self.assertIn('DATE_NAT',r['failure_codes']);self.assertEqual(bad.tables['handoff/keys_meta.csv'][0]['split'],'unknown');evidence={'priority':'invalid_key before date','all_reasons_retained':r['failure_codes']}
            elif n==6:
                self.assertEqual(set(self.x),set(self.y));self.assertEqual(set(self.x),{r['appid'] for r in self.data.tables['handoff/x_entity_states.csv']});self.assertEqual(len(self.x),6);evidence={'developed_key_count':6}
            elif n==7:
                dsp=self.data.tables['handoff/row_disposition.csv'];self.assertEqual(self.data.tables['handoff/rows_excluded.csv'],[r for r in dsp if r['disposition']=='excluded_2019']);self.assertEqual({r['disposition'] for r in self.data.tables['handoff/rows_invalid_unknown.csv']},{'invalid_date_nat','uncovered_year'});evidence={'excluded_view':1,'invalid_unknown_view':2}
            elif n==8:
                self.assertEqual([r['appid'] for r in self.data.tables['handoff/x_primary.csv']],sorted(self.x));self.assertEqual(h.key_digest(['001','12']),h.digest_bytes(b'["001","12"]'));self.assertNotEqual(h.key_digest(['1','23']),h.key_digest(['12','3']));evidence={'order':'ASCII lexicographic','digest_ambiguous_concat_rejected':True}
            elif n==9:
                perm=h.build_dataset(list(reversed(self.main)),{k:list(reversed(v)) for k,v in self.aux.items()});self.assertEqual(self.x,{r['appid']:r for r in perm.tables['handoff/x_primary.csv']});self.assertEqual(self.y,{r['appid']:r for r in perm.tables['handoff/y_label.csv']});evidence={'source_order_reversal_invariant_by_appid':True}
            elif n==10:
                bad=h.build_dataset([row('unknown',2017)]);self.assertEqual(bad.tables['handoff/x_primary.csv'],[]);self.assertEqual(bad.tables['handoff/keys_meta.csv'][0]['appid'],None);self.assertEqual(bad.tables['handoff/row_disposition.csv'][0]['source_row_no'],1);evidence={'bad_key_identity_retained':1,'canonical_join_excluded':True}
        elif p=='H05-X':
            columns=self.schema['files']['handoff/x_primary.csv']['columns']
            if n==1:self.assertEqual(columns,['appid',*config.PRIMARY_FEATURE_COLUMNS]);self.assertEqual(len(columns),25);evidence={'feature_count_after_envelope':24,'columns':columns}
            elif n==2:self.assertEqual(self.data.statistics['columns_before_drop'],columns);self.assertEqual(self.data.statistics['columns_after_drop'],columns[1:]);evidence={'explicit_drop':'appid','after':columns[1:]}
            elif n==3:
                bad=deepcopy(self.data);bad.tables['handoff/x_primary.csv'][0]['log_owners_renamed']=4;self.assertEqual(h.validate_dataset(bad)['H05-X-03']['status'],'FAIL');evidence={'renamed_outcome_extra_column_rejected':True}
            elif n==4:
                bad=deepcopy(self.data);bad.tables['handoff/x_primary.csv'][0]['english_missing']=1;self.assertEqual(h.validate_dataset(bad)['H05-X-04']['status'],'FAIL');evidence={'unapproved_missing_indicator_rejected':True}
            elif n==5:self.assertFalse(set(columns[1:])&set(config.SNAPSHOT_SENSITIVITY_COLUMNS));self.assertNotIn('handoff/sensitivity_snapshot.csv',self.manifest['files']);evidence={'snapshot_interface':'OFF'}
            elif n==6:
                r=self.report['checks']['H05-X-06'];self.assertEqual(r['status'],'PASS');self.assertNotIn('steamspy_tag_data.csv',r['evidence']['primary_sources']);evidence=r['evidence']
            elif n==7:self.assertFalse(set(columns[1:])&set(config.METADATA_COLUMNS));evidence={'metadata_removed':list(config.METADATA_COLUMNS)}
            elif n==8:self.assertFalse(self.data.statistics['learned_transforms']);self.assertEqual(set(self.manifest['files']),set(self.manifest['files'])-{'model.pkl','encoder.pkl'});evidence={'fitted_artifacts':[]}
        elif p=='H05-SER':
            if n==1:
                for text in ['NaN','Infinity','{"x":1,"x":2}','[1,]','1e309']:
                    with self.assertRaises(ValueError):h.strict_json_loads(text)
                evidence={'strict_invalid_JSON_cases':5}
            elif n==2:
                spec=self.definitions['handoff/x_primary.csv','required_age']
                for value in [float('nan'),float('inf'),1.0,2**63]:
                    with self.assertRaises(ValueError):h.encode_cell(value,spec)
                self.assertEqual(h.encode_cell(2**63-1,spec),str(2**63-1));evidence={'nonfinite_float_and_overflow_integer_rejected':4,'max_integer_exact':2**63-1}
            elif n==3:
                self.assertIsNone(self.x['15']['platforms']);self.assertEqual(self.x['14']['platforms'],());self.assertEqual(self.x['15']['platform_count'],0);self.assertIs(self.x['15']['has_windows'],False)
                sm={r['appid']:r for r in self.data.tables['handoff/x_entity_states.csv']};self.assertEqual(sm['15']['platforms'],'S_MISSING');self.assertEqual(sm['14']['platforms'],'S_EMPTY_LIST');self.assertEqual(sm['15']['source_missing_classes']['platforms'],'MISSING_DECLARED');evidence={'source_null_vs_empty_array':'distinct','derived_missing_count':0}
            elif n==4:
                spec=self.definitions['handoff/x_primary.csv','developer'];value=('a;b','c,d','q"x','line\nbreak','\\path')
                self.assertEqual(h.decode_cell(h.encode_cell(value,spec),spec),value);self.assertEqual(h.literal_csv(self.directory/'handoff/keys_meta.csv')[0]['name'],self.main[0]['name']);evidence={'special_entity_codec_characters':[';',',','"','newline','backslash'],'raw_CSV_embedded_newline_preserved':True}
            elif n==5:
                for spec,value in [(self.definitions['handoff/x_primary.csv','developer'],('\\N',)),(self.definitions['handoff/keys_meta.csv','name'],'\\N')]:
                    with self.assertRaises(ValueError):h.encode_cell(value,spec)
                decl=self.definitions['manifest/field_dictionary.csv','missing_representation'];self.assertEqual(h.decode_cell(h.encode_cell('\\N',decl),decl),'\\N');evidence={'actual_data_sentinel_collision_blocked':True,'sentinel_declaration_metadata_allowed':True}
            elif n==6:
                path='handoff/x_primary.csv';back=h.read_table(self.directory/path,self.schema['files'][path]['columns'],self.definitions,path);self.assertEqual({r['appid']:r for r in back},self.x)
                bad=deepcopy(self.data);bad.tables[path][0]['release_month']=99;ok,_=h._domain_conversion_check(bad);self.assertFalse(ok)
                with self.assertRaises(ValueError):h.decode_cell('true',self.definitions[path,'required_age'])
                evidence={'full_X_explicit_typed_roundtrip_rows':6,'bad_calendar_and_cast_rejected':True}
            elif n==7:
                payload=(self.directory/'handoff/x_primary.csv').read_bytes();self.assertFalse(payload.startswith(b'\xef\xbb\xbf'));self.assertTrue(payload.startswith(b'"appid","english"'));self.assertNotIn(b'\r\n',payload);evidence={'encoding':'utf8/noBOM','QUOTE_ALL':True,'terminator':'LF'}
            elif n==8:
                sm={r['appid']:r for r in self.data.tables['handoff/x_entity_states.csv']};self.assertEqual(sm['15']['source_missing_classes']['developer'],'MISSING_EMPTY');self.assertEqual(sm['15']['source_missing_classes']['publisher'],'MISSING_WHITESPACE');self.assertEqual(self.meta['15']['raw_parse_values']['publisher'],'   ');evidence={'source_classes':['EMPTY','WHITESPACE','DECLARED'],'captured_before_loss':True}
            elif n==9:
                for v in [None,[],[''],['a;b','q"x','line\nbreak']]:self.assertEqual(h.strict_json_loads(h.json_text(v)),v)
                self.assertNotIn('S_EMPTY_STRING_ELEMENT',{r[f] for r in self.data.tables['handoff/x_entity_states.csv'] for f in config.DATA_PARSE_POLICY['sequences']['fields']});evidence={'four_codec_slots':4,'reserved_slot_source_output':False}
        elif p=='H05-LBL':
            if n==1:
                for illegal in ['-1','+1','1.0','NaN','１２','']:
                    d=h.build_dataset([row('1',2016,positive_ratings=illegal)]);self.assertIsNone(d.tables['handoff/year_cutoffs.csv'][0]['cutoff_value']);self.assertTrue(any(i['blocking'] for i in d.issues))
                self.assertEqual(self.report['overall'],'pass');evidence={'invalid_base_literals_blocked':6,'excluded_NaT_ratings_diagnostic_only':True}
            elif n==2:
                bad=h.build_dataset([row('1',2016,positive_ratings=str(2**63-1),negative_ratings='1')]);self.assertEqual(bad.tables['handoff/year_cutoffs.csv'][0]['computable'],False);self.assertIn('RATINGS_SUM_OVERFLOW',bad.tables['handoff/row_disposition.csv'][0]['failure_codes']);self.assertEqual(self.y['13']['total_ratings'],15);evidence={'checked_sum_overflow':True,'safe_total':15}
            elif n==3:
                bad=h.build_dataset([row('bad',2016),row('2',2016,english='bad'),row('3',2016,positive_ratings='bad')]);self.assertEqual(bad.statistics['base_population_rows'],3);self.assertEqual(bad.tables['handoff/year_cutoffs.csv'][0]['cohort_n'],3);evidence={'population_independent_of_key_feature_rating_masks':3}
            elif n==4:self.assertEqual({k:v['cohort_n'] for k,v in self.cut.items()},{1997:1,2016:2,2017:2,2018:1,2020:1});self.assertEqual(self.cut[2016]['cutoff_value'],14.0);self.assertEqual(self.cut[2017]['cutoff_value'],45.2);evidence={'full_population':7,'cutoff2016':14.0,'cutoff2017':45.2}
            elif n==5:self.assertIsNone(config.MIN_YEAR_GAMES);self.assertEqual(self.y['001']['hit_reviews'],1);self.assertEqual(self.y['16']['hit_reviews'],1);self.assertEqual(config.TARGET_INTERPOLATION,'linear');self.assertIs(config.TARGET_INCLUSIVE,True);evidence={'single_row_early_cohort_retained':True,'cutoff_tie_inclusive':True}
            elif n==6:self.assertEqual(self.data.statistics['population_positive_sum'],5);self.assertEqual(sum(r['positive_n'] for r in self.cut.values()),5);self.assertEqual(sum(r['cohort_n'] for r in self.cut.values()),7);evidence={'population_rows':7,'population_positive':5}
            elif n==7:self.assertEqual(self.data.statistics['developed_positive_sum'],4);self.assertEqual(len(self.x),6);self.assertNotEqual(self.data.statistics['population_positive_sum'],self.data.statistics['developed_positive_sum']);evidence={'developed_rows':6,'developed_positive':4,'population_positive':5}
            elif n==8:
                bad=h.build_dataset([row('1',2017,positive_ratings='bad'),row('2',2017)]);self.assertEqual(bad.tables['handoff/y_label.csv'],[]);self.assertIsNone(bad.tables['handoff/year_cutoffs.csv'][0]['positive_n']);evidence={'indeterminate_cohort_labels_absent':2,'not_filled_zero':True}
            elif n==9:self.assertNotIn('17',self.x);self.assertEqual(self.meta['17']['disposition'],'excluded_2019');self.assertNotIn(2019,self.cut);evidence={'excluded_2019_record_retained':1,'label_not_delivered':True}
            elif n==10:self.assertEqual(self.meta['19']['release_date'],'bad-date');self.assertIsNone(self.meta['19']['release_year']);self.assertNotIn('19',self.y);evidence={'NaT_raw_record_retained':1}
            elif n==11:self.assertEqual(self.meta['18']['disposition'],'uncovered_year');self.assertNotIn('18',self.y);self.assertEqual(self.cut[2020]['cohort_n'],1);evidence={'uncovered_isolated':1,'population_retained':1}
            elif n==12:
                changed=h.build_dataset([*self.main,row('20',2021,positive_ratings='999')],self.aux);cut={r['release_year']:r for r in changed.tables['handoff/year_cutoffs.csv']};self.assertEqual(cut[2016],self.cut[2016]);self.assertEqual(cut[2017],self.cut[2017]);evidence={'new_year_does_not_change_2016_2017_cutoffs':True}
            elif n==13:
                bad=h.build_dataset([row('bad',2017),row('2',2017,positive_ratings='bad')]);pck=h.write_package(bad,self.temp.name);self.assertEqual(pck['report']['overall'],'blocked');self.assertEqual(bad.tables['handoff/year_cutoffs.csv'][0]['cohort_n'],2);self.assertFalse((pck['directory']/'manifest/HANDOFF_READY.json').exists());evidence={'bad_key_and_ratings_block_package':True,'cohort_not_shrunk':2}
        elif p=='H05-HIST':
            if n==1:self.assertTrue(all(e['source_year']<self.meta[e['target_appid']]['release_year'] for e in self.edges));self.assertNotIn('13',{e['source_appid'] for e in self.edges if e['target_appid']=='12'});evidence={'same_year_not_visible':True}
            elif n==2:self.assertFalse(any(e['source_year']==2019 or e['source_appid'] in {'17','18','19'} for e in self.edges));evidence={'future_excluded_unknown_NaT_sources_absent':True}
            elif n==3:
                target=[e['source_appid'] for e in self.edges if e['target_appid']=='14' and e['entity_kind']=='developer'];self.assertEqual(target,['001','12','13']);self.assertEqual(len(target),len(set(target)));evidence={'A_B_A_entity_overlap_sources_once':target,'cross_P05':'P05-ENT-06'}
            elif n==4:
                bad=deepcopy(self.data);bad.tables['handoff/history_source_membership.csv']=[e for e in bad.tables['handoff/history_source_membership.csv'] if not(e['target_appid']=='14' and e['source_appid']=='12' and e['entity_kind']=='developer')];check=h.validate_dataset(bad)['H05-HIST-04'];self.assertEqual(check['status'],'FAIL');self.assertEqual(len(check['evidence']['missing_sources']),1)
                extra=deepcopy(self.data);extra.tables['handoff/history_source_membership.csv'].append(dict(window_variant=h.WINDOW,target_appid='12',entity_kind='developer',source_year=2016,source_appid='13'));self.assertEqual(h.validate_dataset(extra)['H05-HIST-04']['status'],'FAIL');evidence={'missing_and_extra_sources_rejected':True,'cross_P05':'P05-ENT-06'}
            elif n==5:
                win=h.strict_json_loads((self.directory/'handoff/history_windows.json').read_text());self.assertEqual(win['source_bindings'],{p:h.file_hash(self.directory/p) for p in ['handoff/x_primary.csv','handoff/y_label.csv']});self.assertEqual(self.y['13']['hit_reviews'],1);self.assertEqual(self.y['12']['hit_reviews'],0);evidence={'source_bindings':win['source_bindings'],'source_label_join_uses_source_appid':True}
            elif n==6:
                self.assertAlmostEqual(self.x['14']['dev_prior_count'],math.log1p(3),places=12);self.assertAlmostEqual(self.x['14']['dev_prior_hit_rate'],3/13,places=12);self.assertEqual(self.x['15']['dev_prior_count'],0.0);self.assertEqual(self.x['15']['dev_prior_hit_rate'],0.1);evidence={'target14_N':3,'target14_H':2,'rate':3/13,'missing_fallback':[0,0.1]}
            elif n==7:
                win={(r['target_appid'],r['entity_kind']):r for r in self.data.history_windows['target_windows']};self.assertEqual(win['16','developer']['source_max_year'],2017);self.assertIsNone(win['15','developer']['source_max_year']);self.assertEqual(len(win),12);evidence={'target16_source_max':2017,'target15_empty_source_max':None}
            elif n==8:self.assertEqual(self.data.history_windows['window_variant'],h.WINDOW);self.assertAlmostEqual(self.x['16']['dev_prior_count'],math.log1p(4),places=12);self.assertEqual(config.DATA_HANDOFF_POLICY['history_fixed_2016_variant'],'not_adopted_not_a_gate');evidence={'A_includes_relevant_2017_source':True,'B_enabled':False}
        elif p=='H05-AUX':
            coverage={r['aux_table']:r for r in self.data.tables['handoff/aux_coverage.csv']}
            if n==1:self.assertTrue(all(r['main_rows_before']==r['main_rows_after']==9 for r in coverage.values()));self.assertEqual(len(self.x),6);evidence={'source_main_rows_retained':9,'developed_rows_retained':6}
            elif n==2:
                self.assertEqual(coverage['steam_description_data.csv']['extra_keys'],1);self.assertEqual(coverage['steam_requirements_data.csv']['missing_coverage'],7)
                aux=deepcopy(self.aux);aux['steam_media_data.csv']=[{'steam_appid':'1'},{'steam_appid':' 1 '}];bad=h.build_dataset(self.main,aux);pck=h.write_package(bad,self.temp.name);self.assertEqual(pck['report']['overall'],'blocked');evidence={'extra':1,'missing':7,'aux_strip_collision_blocks_package':True}
            elif n==3:self.assertNotIn('steamspy_tag_data.csv',self.report['checks']['H05-AUX-03']['evidence']['primary_feature_sources']);self.assertNotIn('handoff/sensitivity_snapshot.csv',self.manifest['files']);evidence={'tags_never_primary':True,'sensitivity_OFF':True}
            elif n==4:self.assertEqual(self.report['limitation'],h.RETROSPECTIVE_LIMITATION);self.assertIn('retrospective',self.report['limitation']);evidence={'snapshot_limitation':self.report['limitation']}
        elif p=='H05-MAN':
            if n==1:self.assertEqual(len(self.manifest['inputs']),6);self.assertEqual(len(self.manifest['files']),18);self.assertTrue(all(v['sha256']==h.file_hash(self.directory/p) for p,v in self.manifest['files'].items()));evidence={'stable_files':18,'measured_synthetic_inputs':6}
            elif n==2:self.assertIsNone(self.manifest['label']['snapshot_reference']);self.assertIs(self.manifest['label']['documentary_only'],True);self.assertEqual(self.manifest['statistics']['source_records'],9);evidence={'old27075_not_used_for_fixture9':True}
            elif n==3:
                self.assertNotIn('manifest_sha256',self.manifest);self.assertNotIn('report_sha256',self.manifest);self.assertNotIn('manifest/validation_report.json',self.manifest['files']);self.assertEqual(self.report['manifest_sha256'],h.file_hash(self.directory/'manifest/manifest.json'));evidence={'stable_manifest_report_forward_binding_only':True}
            elif n==4:
                bad=h.build_dataset([row('1',2017,name='/Users/synthetic/example')]);pck=h.write_package(bad,self.temp.name);self.assertEqual(pck['report']['checks']['H05-MAN-04']['status'],'FAIL');self.assertEqual(pck['report']['overall'],'fail');self.assertFalse((pck['directory']/'manifest/HANDOFF_READY.json').exists());evidence={'personal_absolute_path_blocks_marker':True}
            elif n==5:
                self.assertEqual(self.manifest['versions']['design'],'v1.2');self.assertEqual(self.manifest['versions']['business_base'],'v1.1');snap=h.strict_json_loads((self.directory/'manifest/design_contract_snapshot.json').read_text());self.assertEqual(snap['config_sha256'],h.file_hash(h.ROOT/'config.py'));evidence={'design_version':'v1.2','business_base':'v1.1','config_sha256':snap['config_sha256']}
            elif n==6:self.assertEqual(set(self.manifest['git']['relevant_code_sha256']),set(h.RELEVANT_CODE));self.assertTrue(all(v==h.file_hash(h.ROOT/p) for p,v in self.manifest['git']['relevant_code_sha256'].items()));self.assertRegex(self.manifest['git']['HEAD'],r'^[0-9a-f]{40}$');evidence=self.manifest['git']
            elif n==7:self.assertEqual(self.manifest['runtime']['pandas'],h.pd.__version__);self.assertEqual(self.manifest['runtime']['numpy'],h.np.__version__);self.assertRegex(self.manifest['runtime']['python'],r'^\d+\.\d+');evidence=self.manifest['runtime']
            elif n==8:self.assertEqual(self.manifest['versions']['parse_policy_ref']['version'],'steam-parse/v1');self.assertEqual(self.manifest['versions']['parse_policy_ref']['document_sha256'],h.file_hash(self.directory/'manifest/parse_contract.md'));evidence=self.manifest['versions']['parse_policy_ref']
        elif p=='H05-GATE':
            if n==1:
                failed=dict(scope='real-file',overall='fail',unresolved_policy=False,checks={'x':{'status':'FAIL'}});self.assertIsNone(h.ready_binding('a'*64,'b'*64,failed));self.assertFalse((self.directory/'manifest/HANDOFF_READY.json').exists());evidence={'failed_marker_ineligible':True,'synthetic_formal_READY_absent':True}
            elif n==2:
                other=h.write_package(self.data,self.temp.name);self.assertNotEqual(other['directory'],self.directory);self.assertRegex(other['directory'].name,r'^\d{8}T\d{6}_\d{6}Z$')
                before=dict(self.manifest['inputs']);self.assertEqual(before,h._input_fingerprints(self.data));evidence={'fresh_UTC_directory':other['directory'].name,'six_synthetic_inputs_unchanged':True,'physical_raw_STEP1_not_accessed':True}
            elif n==3:self.assertEqual(self.report['checks'][identifier]['evidence']['seal_order'],['candidate_validated','stable_sealed_and_byte_compared','manifest_frozen','report_prepared']);self.assertTrue(self.report['checks'][identifier]['evidence']['READY_last_if_real_eligible']);evidence=self.report['checks'][identifier]['evidence']
            elif n==4:self.assertFalse(h.verify_package(self.directory)['accepted_for_formal_handoff']);self.assertEqual(config.DATA_HANDOFF_POLICY['mutable_pointer'],'OFF');self.assertFalse((h.ROOT/'data/processed/CURRENT_HANDOFF.json').exists());evidence={'candidate_and_synthetic_not_formal':True,'mutable_pointer_OFF':True}
            elif n==5:
                report_before=h.file_hash(self.directory/'manifest/validation_report.json');v=h.verify_package(self.directory,require_real=False,marker=_virtual_marker(self.directory));self.assertEqual(v['overall'],'pass');self.assertEqual(len(v['checks']),7);self.assertTrue(all(v['checks'].values()));self.assertFalse(v['accepted_for_formal_handoff']);self.assertEqual(report_before,h.file_hash(self.directory/'manifest/validation_report.json'));self.assertEqual(h.verify_package(self.directory,marker=_virtual_marker(self.directory))['overall'],'fail');evidence={'seven_synthetic_component_checks':v['checks'],'formal_scope_rejected':True,'sealed_report_unchanged':True}
            elif n==6:
                clone=Path(self.temp.name)/'tampered';shutil.copytree(self.directory,clone);marker=_virtual_marker(clone);path=clone/'handoff/y_label.csv';path.write_bytes(path.read_bytes()+b'\n');v=h.verify_package(clone,require_real=False,marker=marker);self.assertFalse(v['checks']['stable_hashes'])
                clone2=Path(self.temp.name)/'tampered_report';shutil.copytree(self.directory,clone2);marker2=_virtual_marker(clone2);p2=clone2/'manifest/validation_report.json';p2.write_bytes(p2.read_bytes()+b' ');v2=h.verify_package(clone2,require_real=False,marker=marker2);self.assertFalse(v2['checks']['report_binding']);evidence={'stable_and_report_layer_tamper_rejected':True}
            elif n==7:self.assertEqual(self.report['scope'],'synthetic');self.assertIsNone(h.ready_binding('a'*64,'b'*64,self.report));self.assertIs(self.report['ready_eligible'],False);evidence={'synthetic_pass_is_not_real_file_acceptance':True}
            elif n==8:
                baseline=json.loads((h.ROOT/'tests/fixtures/v12_baseline.json').read_text());self.assertEqual(h.file_hash(h.ROOT/'scripts/stage0_precheck.py'),baseline['legacy_sha256']['scripts/stage0_precheck.py']);self.assertEqual(self.report['checks'][identifier]['evidence']['external_actions'],[]);evidence={'legacy_SHA_unchanged':True,'external_actions':[],'old_exit4_semantics_preserved':True}
        else:raise AssertionError('Unknown hardcoded H05 test '+identifier)
        self.assertTrue(evidence,'Missing concrete acceptance evidence')
        self.record(identifier,evidence)


# This fixed list is independent of the machine contract index used by the runner.
H05_TEST_IDS=tuple([f'H05-KEY-{i:02}' for i in range(1,11)]+[f'H05-X-{i:02}' for i in range(1,9)]+
    [f'H05-SER-{i:02}' for i in range(1,10)]+[f'H05-LBL-{i:02}' for i in range(1,14)]+
    [f'H05-HIST-{i:02}' for i in range(1,9)]+[f'H05-AUX-{i:02}' for i in range(1,5)]+
    [f'H05-MAN-{i:02}' for i in range(1,9)]+[f'H05-GATE-{i:02}' for i in range(1,9)])
for _id in H05_TEST_IDS:
    def _method(self,identifier=_id):self.case(identifier)
    _method.__name__='test_'+_id.replace('-','_').lower()
    setattr(HandoffAssertions,_method.__name__,_method)


class FailureRegressions(unittest.TestCase):
    def test_native_auxiliary_keys_and_tag_collisions(self):
        main,aux=fixture()
        data=h.build_dataset(main,aux)
        self.assertEqual(data.key_audits['steamspy_tag_data.csv']['strip_cardinality'],2)
        for name in h.SOURCE_NAMES[1:]:
            changed=deepcopy(aux)
            wrong='steam_appid' if name=='steamspy_tag_data.csv' else 'appid'
            changed[name]=[{wrong:'001'}]
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'SOURCE_SCHEMA'):
                h.build_dataset(main,changed)
        aux['steamspy_tag_data.csv']=[{'appid':'1'},{'appid':' 1 '}]
        with tempfile.TemporaryDirectory() as t:
            receipt=h.write_package(h.build_dataset(main,aux),t)
            self.assertEqual(receipt['report']['overall'],'blocked')
            self.assertFalse((receipt['directory']/'manifest/HANDOFF_READY.json').exists())

    def test_history_reconstruction_matches_cartesian_raw_oracle(self):
        from unittest.mock import patch
        main,aux=fixture()
        main.extend([row('20',2017,developer='A;B;a'),row('21',2018,developer='a;B'),
                     row('22',2018,developer=';;',publisher='unknown')])
        data=h.build_dataset(main,aux)
        meta={r['appid']:r for r in data.tables['handoff/keys_meta.csv'] if r['split'] in ('train','validation','test')}
        expected=set()
        for target,m in meta.items():
            for kind in ('developer','publisher'):
                entities=set(h.parse_sequence(m['raw_parse_values'][kind],kind).value or ())
                for source,s in meta.items():
                    members=set(h.parse_sequence(s['raw_parse_values'][kind],kind).value or ())
                    if s['release_year']<m['release_year'] and entities&members:
                        expected.add((h.WINDOW,target,kind,s['release_year'],source))
        actual={tuple(r[k] for k in ('window_variant','target_appid','entity_kind','source_year','source_appid'))
                for r in data.tables['handoff/history_source_membership.csv']}
        self.assertEqual(expected,actual)
        self.assertTrue(any(e[1]=='21' and e[3]==2017 for e in actual))
        self.assertFalse(any(e[3]==2019 for e in actual))
        with patch.object(h,'parse_sequence',wraps=h.parse_sequence) as parser:
            checks=h.validate_dataset(data)
        self.assertTrue(all(v['status']=='PASS' for k,v in checks.items() if k.startswith('H05-HIST-')))
        # Other domain checks also parse source sequences. The checker remains
        # linear in source rows, rather than parsing the Cartesian source pairs.
        self.assertLessEqual(parser.call_count,12*len(main))

    def test_formal_output_path_guard_runs_before_creating_or_reading(self):
        data=h.build_dataset([row('1',2016)])
        with tempfile.TemporaryDirectory() as t:
            outside=Path(t)/'protected'
            with self.assertRaisesRegex(ValueError,'output must be outputs/data_handoff'):
                h.write_package(data,outside,scope='real-file',input_files={n:Path(t)/n for n in h.SOURCE_NAMES},protected_paths={'STEP1':outside})
            self.assertFalse(outside.exists())

    def test_int64_upper_ratings_follow_frozen_pandas_comparison(self):
        from scripts.validate_steam_data import prepare_analytical
        top=2**63-1
        for totals in [[top],[top,top],[top-1,top],[top-2,top-1,top],[2**53,2**53+1]]:
            with self.subTest(totals=totals):
                main=[row(str(i),2016,positive_ratings=str(total)) for i,total in enumerate(totals,1)]
                data=h.build_dataset(main)
                actual=[r['hit_reviews'] for r in data.tables['handoff/y_label.csv']]
                self.assertEqual(actual,[1]*len(totals))
                frame=h.pd.DataFrame(main)
                for f in ['positive_ratings','negative_ratings']:frame[f]=frame[f].astype('int64')
                self.assertEqual(actual,prepare_analytical(frame)['hit_reviews'].tolist())
                self.assertEqual(data.tables['handoff/year_cutoffs.csv'][0]['positive_n'],len(totals))
                self.assertTrue(all(c['status']=='PASS' for k,c in h.validate_dataset(data).items() if k.startswith('H05-LBL-')))

    def test_canonical_key_cannot_be_remapped_away_from_source(self):
        data=h.build_dataset([row('1',2016)])
        for path in ['handoff/x_primary.csv','handoff/y_label.csv','handoff/x_entity_states.csv','handoff/keys_meta.csv']:
            data.tables[path][0]['appid']='2'
        for w in data.history_windows['target_windows']:w['target_appid']='2'
        self.assertEqual(h.validate_dataset(data)['H05-KEY-03']['status'],'FAIL')

    def test_metadata_disposition_must_match_each_source_identity(self):
        cases=[('train_to_test',[row('1',2016)],[(0,'test','test')]),
               ('train_to_validation',[row('1',2016)],[(0,'validation','validation')]),
               ('swapped_sources',[row('1',2016),row('2',2018)],[(0,'test','test'),(1,'train','train')]),
               ('excluded_to_uncovered',[row('1',2019)],[(0,'uncovered_year','unknown')]),
               ('uncovered_to_excluded',[row('1',2020)],[(0,'excluded_2019','excluded')])]
        for name,main,changes in cases:
            with self.subTest(case=name),tempfile.TemporaryDirectory() as t:
                data=h.build_dataset(main)
                meta=data.tables['handoff/keys_meta.csv']
                original_counts=Counter(r['disposition'] for r in meta)
                for index,disposition,split in changes:
                    meta[index].update(disposition=disposition,split=split)
                if name=='swapped_sources':
                    self.assertEqual(Counter(r['disposition'] for r in meta),original_counts)
                receipt=h.write_package(data,t,issue_ready=True)
                self.assertEqual(receipt['report']['checks']['H05-KEY-05']['status'],'FAIL')
                self.assertEqual(receipt['report']['overall'],'blocked')
                self.assertFalse((receipt['directory']/'manifest/HANDOFF_READY.json').exists())

    def test_metadata_disposition_binding_uses_identity_not_row_position(self):
        data=h.build_dataset([row('1',2016),row('2',2018)])
        data.tables['handoff/keys_meta.csv'].reverse()
        checks=h.validate_dataset(data)
        self.assertEqual(checks['H05-KEY-05']['status'],'PASS')
        self.assertEqual(checks['H05-KEY-08']['status'],'FAIL')

    def test_invalid_metadata_source_row_returns_blocked_diagnostics(self):
        for source_row_no in (0,-1,2,None,'1',True):
            with self.subTest(source_row_no=source_row_no),tempfile.TemporaryDirectory() as t:
                data=h.build_dataset([row('1',2016)])
                data.tables['handoff/keys_meta.csv'][0]['source_row_no']=source_row_no
                receipt=h.write_package(data,t,issue_ready=True)
                self.assertEqual(receipt['report']['overall'],'blocked')
                self.assertIn('SOURCE_IDENTITY',receipt['report']['error'])
                self.assertEqual(len(receipt['report']['checks']),68)
                report_path=receipt['directory']/'diagnostics/validation_report.json'
                self.assertTrue(report_path.is_file())
                self.assertEqual(h.strict_json_loads(report_path.read_text(encoding='utf-8')),receipt['report'])
                self.assertFalse((receipt['directory']/'manifest').exists())
                self.assertFalse((receipt['directory']/'candidate').exists())

    def test_virtual_marker_never_authorizes_formal_scope_and_wrong_ids_rejected(self):
        data=h.build_dataset([row('1',2016)])
        with tempfile.TemporaryDirectory() as t:
            receipt=h.write_package(data,t);directory=receipt['directory']
            p=directory/'manifest/manifest.json';manifest=json.loads(p.read_text());manifest['scope']='real-file';p.write_text(h.json_text(manifest)+'\n')
            p=directory/'manifest/validation_report.json';report=json.loads(p.read_text());report['scope']='real-file';report['manifest_sha256']=h.file_hash(directory/'manifest/manifest.json');p.write_text(h.json_text(report)+'\n')
            self.assertFalse(h.verify_package(directory,marker=_virtual_marker(directory))['accepted_for_formal_handoff'])
            self.assertFalse(h.verify_package(directory)['accepted_for_formal_handoff'])
            receipt=h.write_package(data,t);directory=receipt['directory']
            p=directory/'manifest/validation_report.json';report=json.loads(p.read_text());report['checks']['H05-WRONG-01']=report['checks'].pop('H05-KEY-01');p.write_text(h.json_text(report)+'\n')
            self.assertFalse(h.verify_package(directory,require_real=False,marker=_virtual_marker(directory))['checks']['no_block_or_open'])
            self.assertIsNone(h.ready_binding('a'*64,'b'*64,dict(report,scope='real-file')))

    def test_missing_required_column_returns_blocked_diagnostics(self):
        main,aux=fixture();data=h.build_dataset(main,aux)
        del data.tables['handoff/x_primary.csv'][0]['developer']
        with tempfile.TemporaryDirectory() as t:
            receipt=h.write_package(data,t)
            self.assertEqual(receipt['report']['overall'],'blocked')
            self.assertTrue((receipt['directory']/'diagnostics/validation_report.json').is_file())
            self.assertFalse((receipt['directory']/'manifest/HANDOFF_READY.json').exists())

    def test_label_source_trace_and_per_year_counts_cannot_be_forged(self):
        main,aux=fixture();original=h.build_dataset(main,aux)
        for column,value,identifier in [('positive_ratings',2,'H05-LBL-02'),
                ('cohort_n',999,'H05-LBL-07'),('positive_in_cohort',999,'H05-LBL-07'),
                ('cutoff_value',999.0,'H05-LBL-07')]:
            with self.subTest(column=column):
                data=deepcopy(original);data.tables['handoff/y_label.csv'][0][column]=value
                self.assertEqual(h.validate_dataset(data)[identifier]['status'],'FAIL')
        data=deepcopy(original);data.tables['handoff/year_cutoffs.csv'][0]['positive_n']=999
        self.assertEqual(h.validate_dataset(data)['H05-LBL-06']['status'],'FAIL')

    def test_cohort_window_digest_parameters_and_nonfinite_history_rejected(self):
        main,aux=fixture();original=h.build_dataset(main,aux)
        for column,value in [('membership_digest','0'*64),('parameters',{}),('source_years',[2099])]:
            with self.subTest(column=column):
                data=deepcopy(original);data.history_windows['cohort_windows'][0][column]=value
                self.assertEqual(h.validate_dataset(data)['H05-HIST-07']['status'],'FAIL')
        data=deepcopy(original);data.tables['handoff/x_primary.csv'][0]['dev_prior_count']=float('nan')
        self.assertEqual(h.validate_dataset(data)['H05-HIST-06']['status'],'FAIL')

    def test_history_missing_source_blocks_write(self):
        main,aux=fixture();data=h.build_dataset(main,aux);data.tables['handoff/history_source_membership.csv'].pop()
        with tempfile.TemporaryDirectory() as t:
            receipt=h.write_package(data,t);self.assertEqual(receipt['report']['overall'],'blocked');self.assertFalse((receipt['directory']/'manifest/HANDOFF_READY.json').exists())

    def test_invalid_source_feature_cannot_become_legal_missing(self):
        data=h.build_dataset([row('1',2017,required_age='-1')]);data.issues=[]
        with tempfile.TemporaryDirectory() as t:
            receipt=h.write_package(data,t);self.assertEqual(receipt['report']['overall'],'blocked');self.assertEqual(receipt['report']['checks']['H05-SER-06']['status'],'FAIL')

    def test_no_default_real_production_and_no_marker_for_synthetic(self):
        data=h.build_dataset([row('1',2017)])
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(ValueError):h.write_package(data,t,scope='real-file')
            receipt=h.write_package(data,t,scope='synthetic',issue_ready=True);self.assertFalse((receipt['directory']/'manifest/HANDOFF_READY.json').exists())

    def test_csv_field_dictionary_has_actual_enabled_rows_only(self):
        data=h.build_dataset([row('1',2017)])
        with tempfile.TemporaryDirectory() as t:
            receipt=h.write_package(data,t);defs=h.literal_csv(receipt['directory']/'manifest/field_dictionary.csv');schema=h.strict_json_loads((receipt['directory']/'manifest/handoff_schema.json').read_text())
            actual={(r['file'],r['column']) for r in defs};expected={(p,n) for p,v in schema['files'].items() if v['shape']=='CSV_table' for n in v['columns']};self.assertEqual(actual,expected);self.assertNotIn('handoff/raw_provenance.csv',{r['file'] for r in defs})

    def test_source_files_and_fake_step1_protected_on_synthetic_write(self):
        main,aux=fixture()
        with tempfile.TemporaryDirectory() as t:
            parent=Path(t);inputs={}
            for name,records in {'steam.csv':main,**aux}.items():
                p=parent/name;columns=list(records[0]) if records else ['steam_appid']
                with p.open('w',encoding='utf-8',newline='') as f:
                    w=csv.DictWriter(f,fieldnames=columns,quoting=csv.QUOTE_ALL,lineterminator='\n');w.writeheader();w.writerows(records)
                inputs[name]=p
            step=parent/'fake_step1';step.mkdir();(step/'old.txt').write_text('synthetic protected artifact')
            before={k:h.file_hash(p) for k,p in inputs.items()};receipt=h.write_package(h.build_dataset(main,aux),parent/'synthetic_output',input_files=inputs,protected_paths={'STEP1':step})
            self.assertEqual(receipt['report']['overall'],'pass');self.assertEqual(before,{k:h.file_hash(p) for k,p in inputs.items()});self.assertEqual((step/'old.txt').read_text(),'synthetic protected artifact')

    def test_readback_rejects_wrong_header_bool_and_duplicated_JSON(self):
        schema,defs=h._load_spec();spec=defs['handoff/x_primary.csv','has_windows']
        with self.assertRaises(ValueError):h.decode_cell('True',spec)
        with self.assertRaises(ValueError):h.decode_cell('{"x":1,"x":2}',defs['handoff/keys_meta.csv','raw_parse_values'])
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'bad.csv';p.write_text('"wrong"\n"1"\n')
            with self.assertRaises(ValueError):h.read_table(p,schema['files']['handoff/x_primary.csv']['columns'],defs,'handoff/x_primary.csv')

    def test_long_fields_survive_package_readback_and_restore_csv_limit(self):
        original_limit=csv.field_size_limit();custom_limit=1024
        zero_prefix='0'*140000;key=zero_prefix+'12'
        name='quoted,"name"\n'*12000
        main=[row(key,2016,name=name,required_age=zero_prefix+'12')]
        try:
            csv.field_size_limit(custom_limit)
            with tempfile.TemporaryDirectory() as t:
                receipt=h.write_package(h.build_dataset(main),t)
                self.assertEqual(receipt['report']['overall'],'pass')
                self.assertEqual(csv.field_size_limit(),custom_limit)
                schema,defs=h._load_spec()
                p='handoff/x_primary.csv'
                x=h.read_table(receipt['directory']/p,schema['files'][p]['columns'],defs,p)
                self.assertEqual(x[0]['appid'],key)
                self.assertEqual(x[0]['required_age'],12)
                self.assertEqual(csv.field_size_limit(),custom_limit)
                p='handoff/keys_meta.csv'
                meta=h.read_table(receipt['directory']/p,schema['files'][p]['columns'],defs,p)
                self.assertEqual(meta[0]['appid'],key)
                self.assertEqual(meta[0]['raw_appid'],key)
                self.assertEqual(meta[0]['name'],name)
                self.assertEqual(meta[0]['raw_parse_values']['required_age'],zero_prefix+'12')
                self.assertEqual(csv.field_size_limit(),custom_limit)
        finally:
            csv.field_size_limit(original_limit)

    def test_readback_restores_csv_limit_after_long_malformed_record(self):
        schema,defs=h._load_spec();p='handoff/x_primary.csv'
        columns=schema['files'][p]['columns']
        original_limit=csv.field_size_limit();custom_limit=1024
        try:
            csv.field_size_limit(custom_limit)
            with tempfile.TemporaryDirectory() as t:
                path=Path(t)/'long_bad_shape.csv'
                with path.open('w',encoding='utf-8',newline='') as stream:
                    writer=csv.writer(stream,quoting=csv.QUOTE_ALL,lineterminator='\n')
                    writer.writerow(columns)
                    writer.writerow(['0'*140000+'12']+['']*len(columns))
                with self.assertRaisesRegex(ValueError,'SCHEMA_COLUMNS'):
                    h.read_table(path,columns,defs,p)
                self.assertEqual(csv.field_size_limit(),custom_limit)
        finally:
            csv.field_size_limit(original_limit)
