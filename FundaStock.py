# -*- coding: utf-8 -*-
"""
Created on Thu Apr 16 20:42:17 2020

@author: wudi
"""
import pandas as pd
import numpy as np
from Toolbox import DataCollect
from Toolbox import WeightScheme
from MSSQL import MSSQL
from Toolbox import ReturnCal
from Toolbox import DataStructuring 
from Querybase import Query
from scipy import stats
from itertools import chain
from Quant import Optimize
from HotStock import SecR

DC=DataCollect()
RC=ReturnCal()
DS=DataStructuring()
Q=Query()
WS=WeightScheme()
Opt=Optimize()
SR=SecR()
#rebaldaylist=DC.Rebaldaylist(startdate,rebal_period)
class Prep():
    def __init__(self):
        pass
    
    #use the query in Querybase to download hitorical signal
    def Funda_download(self,startdate,signal):
        ms = MSSQL(host="GS-UATVDBSRV01\GSUATSQL",user="sa",pwd="SASThom111",db="JYDBBAK")
        query=getattr(Q,signal)(startdate)
        reslist=ms.ExecQuery(query)
        df=pd.DataFrame(reslist,columns=['publdate','enddate','ticker','sigvalue'])
        return(df)

#use the query in Querybase to download hitorical for valuation related signals only
    def ValuationReciprocal_download(self,rebaldaylist,signal):
        ms = MSSQL(host="GS-UATVDBSRV01\GSUATSQL",user="sa",pwd="SASThom111",db="JYDBBAK")
        sql=[]
        for rebalday in rebaldaylist:
            sqlpart=getattr(Q,'Valuation_Reciprocal')(signal,rebalday)
            sql.append(sqlpart)
        reslist=ms.ExecListQuery(sql)
        df=pd.DataFrame(reslist,columns=['publdate','enddate','ticker','sigvalue'])
        df['sigvalue']=df['sigvalue'].astype(float)
        df['sigvalue']=df['sigvalue'].round(5)
        return(df)

#Prepare the data: Download the underlying signal data, and stack them into one dataframe
    def SigdataPrep(self,dailyreturn,siglist,rebaldaylist):
        startdate=rebaldaylist[0]
        sighist=pd.DataFrame(columns=['publdate','enddate','ticker','sigvalue','signame'])
        for signal in siglist:
            print('downloading:'+signal)
            if signal in (['PE','PB','PCF','PS']):
                sigtab=self.ValuationReciprocal_download(rebaldaylist,signal)
                sigtab=sigtab.loc[sigtab['publdate'].isin(rebaldaylist),:]
            elif signal in (['turnoverweek']):                                           #Market relevant signals, from the dailyreturn file
                sigtab=dailyreturn.loc[dailyreturn['date'].isin(rebaldaylist),['date','ticker',signal]].copy()
                sigtab[signal]=1/sigtab[signal]                                          #The reciprocal of turnover is positively correlated with P&L
                sigtab['publdate']=sigtab['date']
                sigtab=sigtab.rename(columns={'date':'enddate'})
                sigtab=sigtab.rename(columns={signal:'sigvalue'})
                sigtab=sigtab[['publdate','enddate','ticker','sigvalue']]
            elif signal in (['RSI24d']):
                sigtab=pd.DataFrame(columns=['date','ticker','RSI'])
                for rebalday in rebaldaylist:
                    newrsitab=DC.RSI24(dailyreturn,rebalday)
                    sigtab=sigtab.append(newrsitab)
                sigtab['publdate']=sigtab['date']
                sigtab.columns=['enddate','ticker','sigvalue','publdate']
                sigtab=sigtab[['publdate','enddate','ticker','sigvalue']]
            elif signal in (['RSIB']):
                sigtab=pd.DataFrame(columns=['publdate','enddate','ticker','RSIB'])
                for rebalday in rebaldaylist:
                    print(rebalday)
                    newrsitab=DC.RSI_Db(rebalday)
                    sigtab=sigtab.append(newrsitab)
                sigtab.columns=['publdate','enddate','ticker','sigvalue']
            elif signal in (['SectorAlpha']):
                sigtab=DC.LStermSec(rebaldaylist)              #180/10day signal combined
                #sigtab=DC.StockSectorCumreturn(rebaldaylist,'ITD') #ITD return as a signal
                sigtab.columns=['enddate','ticker','primecode','sigvalue']
                sigtab.insert(0,column='publdate',value=sigtab['enddate'])
                sigtab=sigtab[['publdate','enddate','ticker','sigvalue']]
            elif signal in (['Hotsector']):
                sigtab=SR.HotsectorSignal(dailyreturn,rebaldaylist)
                sigtab.columns=['enddate','ticker','pirmecode','sigvalue']
                sigtab.insert(0,column='publdate',value=sigtab['enddate'])
                sigtab=sigtab[['publdate','enddate','ticker','sigvalue']]
            else:
                sigtab=self.Funda_download(startdate,signal)
            sigtab['signame']=signal
            sigtab['ticker']=sigtab['ticker'].astype(str)
            sighist=sighist.append(sigtab,ignore_index=True,sort=False)
        sighist=sighist.loc[sighist['sigvalue'].isnull()==False,:]
        sighist=sighist.sort_values(by=['ticker','publdate'],ascending=[True,True])
        sighist=sighist.loc[sighist['ticker'].str[0].isin(['6','0','3'])]           #Ashs only 6:shanghai,0:shenzhen,3:Chinext
        sighist['publdate']=pd.to_datetime(sighist['publdate'])
        return(sighist)

#Put all 5Q's pnl into one dataframe, each signal has its own datafarme of daily PNL        
    def PNLC(self,dailyreturn,portdict):
        #portdict={k:pd.DataFrame(v,columns=['ticker','mcap','Q','date','PortNav%'])for k,v in portdict.items()} #APply functiton to lists
        portPNL={k:RC.DailyPNL(dailyreturn,v)for k,v in portdict.items()}
        portCumPNL={k:np.exp(np.log1p(v['dailyreturn']).cumsum())for k,v in portPNL.items()}
        portCumPNL={k:np.exp(np.log1p(v['dailyreturn']).cumsum())for k,v in portPNL.items()}
        PNLdict={}
        itemlist=portdict.keys()
        facnamelist=[x.split('_')[0]for x in itemlist]
        facnamelist=list(set(facnamelist))
        for facname in facnamelist:
            tempdict={}
            for qn in list(range(1,6)):
                tempdict[qn]=portCumPNL[facname+'_'+str(qn)]
            PNLdict[facname]=pd.DataFrame.from_dict(tempdict)
            PNLdict[facname].insert(0,column='date',value=portPNL[facname+'_1']['date'])            
        return(PNLdict)

class Funda():
    def __init__(self):
        self.P=Prep()
    
    #Construct a dataframe to be used for neutrliaztion (single signal single rebalday)
    def Current_one_signal(self,sig,current_sig,rebalday,Mcap_rebalday,stock_sector):
        current_onesig=current_sig.loc[(current_sig['publdate']<=rebalday)&(current_sig['signame']==sig),['publdate','ticker','sigvalue','signame']]
        current_onesig=current_onesig.sort_values(by=['publdate','ticker'],ascending=[True,True])    
        current_onesig=current_onesig.drop_duplicates(['ticker'],keep="last")                            #Take entries that are closest to rebalday of each stock
        current_onesigWS=DS.Winsorize(current_onesig,'sigvalue',0.015)                                         #Winsorize a given column
        current_onesigWSMcap=pd.merge(current_onesigWS,Mcap_rebalday[['ticker','mcap']],on='ticker',how='left')  #Add Mcap
        current_onesigWSMcapSec=pd.merge(current_onesigWSMcap,stock_sector.loc[stock_sector['date']==rebalday,['ticker','primecode']],on='ticker',how='left') #Add Sector
        #current_onesigWSMcapSec=current_onesigWSMcapSec[~current_onesigWSMcapSec['primecode'].isin(['40','41'])] #NONFIG stocks only
        indu_dummy=pd.get_dummies(current_onesigWSMcapSec['primecode'])
        current_onesigWSMcapDummy=pd.concat([current_onesigWSMcapSec,indu_dummy],axis=1)                  #Add dummy table
        current_onesigWSMcapDummy=current_onesigWSMcapDummy.replace(np.inf,np.nan)
        current_onesigWSMcapDummy=current_onesigWSMcapDummy.dropna()                                      #Dropna and np.inf
        current_onesigWSMcapDummy['sigvalue']=current_onesigWSMcapDummy['sigvalue'].astype(float)         
        current_onesigWSMcapDummy['mcap']=current_onesigWSMcapDummy['mcap'].astype(float)
        Xset=list(indu_dummy.columns.insert(0,'mcap'))
        return(current_onesigWSMcapDummy,Xset)
    
    #Input: signalhist,sechist. Loop through every rebalday,on every rebalday, loop through Selectsigs,neutralize every signal in Selectsigs
    #Return: A dictionary of every signal's neutralized value and its Zscore on every rebalday
    def NSighist(self,dailyreturn,rebaldaylist,sighist,selectsigs):
        sighist=sighist.loc[sighist['sigvalue'].isnull()==False,:]
        tickerlist=sighist['ticker'].unique().tolist()
        stock_sector=DC.Stock_sector(rebaldaylist,tickerlist,'CITIC')
        rdailyreturn=dailyreturn.loc[dailyreturn['date'].isin(rebaldaylist),:].copy()
        rdailyreturn['mcap']=rdailyreturn['mcap'].apply(np.log)
        nsigdict={}
        for rebalday in rebaldaylist:
            print(rebalday)
            activestocks_rebalday=dailyreturn.loc[(dailyreturn['date']==rebalday)&(dailyreturn['turnoverweek']!=0),:]['ticker'].unique().tolist() #stocks that are tradign on rebalday
            rebaldatetime=pd.to_datetime(rebalday)
            sighist['updatelag']=(sighist['publdate']-rebaldatetime).dt.days                                   #current sig is the snapshot of siglist in the last ENDdate prior to rebal day
            current_sig=sighist.loc[(sighist['updatelag']>=-180)&(sighist['updatelag']<=0),:].copy()                  #remove the entries where publish dates is more than half a year ago
            current_sig=current_sig.loc[current_sig['ticker'].isin(activestocks_rebalday),:]                   #only stocks tradign on rebalday participate in the analysis
            Mcap_rebalday=rdailyreturn.loc[(rdailyreturn['date']==rebalday)&(rdailyreturn['ticker'].isin(current_sig['ticker'].unique())),:].copy()
            Mcap_rebalday=Mcap_rebalday.loc[Mcap_rebalday['mcap']>np.percentile(Mcap_rebalday['mcap'],30),:].copy()
            current_sig=current_sig.loc[current_sig['ticker'].isin(Mcap_rebalday['ticker']),:]
            for sig in selectsigs:
                current_onesigWSMcapDummy,Xset=self.Current_one_signal(sig,current_sig,rebalday,Mcap_rebalday,stock_sector) #Prepare the table with sector dummy and marketcap, to be neutrliazed
                if sig in ['SectorAlpha','HotSector']:
                    Xset=['mcap']
                sig_rebalday=DS.Neutralization(current_onesigWSMcapDummy,sig,Xset)                                          #Neutralized sig values
                sig_rebalday=sig_rebalday.rename(columns={'sigvalue':sig})
                sig_rebalday=DS.Winsorize(sig_rebalday,'N_'+sig,0.05) 
                sig_rebalday[sig+'_zscore']=stats.zscore(sig_rebalday['N_'+sig])
                if sig=='SectorAlpha':
                    eightypercentile=np.percentile(sig_rebalday[sig+'_zscore'],80) #85 has the best monotonicity so far
                    sig_rebalday.loc[sig_rebalday[sig+'_zscore']>=eightypercentile,sig+'_zscore']= sig_rebalday.loc[sig_rebalday[sig+'_zscore']>=eightypercentile,sig+'_zscore']-eightypercentile
                nsigdict[sig+'_'+rebalday]=sig_rebalday
        return(nsigdict)
    
    #Test stocks in a particular universe. ThreeFour is the universe's historical membs: date and tickers
    def NSighistTEST(self,dailyreturn,rebaldaylist,sighist,selectsigs,ThreeFour):
        sighist=sighist.loc[sighist['sigvalue'].isnull()==False,:]
        tickerlist=sighist['ticker'].unique().tolist()
        stock_sector=DC.Stock_sector(rebaldaylist,tickerlist,'CITIC')
        rdailyreturn=dailyreturn.loc[dailyreturn['date'].isin(rebaldaylist),:].copy()
        rdailyreturn['mcap']=rdailyreturn['mcap'].apply(np.log)
        nsigdict={}
        for rebalday in rebaldaylist:
            print(rebalday)
            activestocks_rebalday=ThreeFour.loc[(ThreeFour['date']==rebalday),:]['ticker'].unique().tolist() #stocks that are tradign on rebalday
            rebaldatetime=pd.to_datetime(rebalday)
            sighist['updatelag']=(sighist['publdate']-rebaldatetime).dt.days                                   #current sig is the snapshot of siglist in the last ENDdate prior to rebal day
            current_sig=sighist.loc[(sighist['updatelag']>=-180)&(sighist['updatelag']<=0),:].copy()                  #remove the entries where publish dates is more than half a year ago
            current_sig=current_sig.loc[current_sig['ticker'].isin(activestocks_rebalday),:]                   #only stocks tradign on rebalday participate in the analysis
            Mcap_rebalday=rdailyreturn.loc[(rdailyreturn['date']==rebalday)&(rdailyreturn['ticker'].isin(current_sig['ticker'].unique())),:].copy()
            #Mcap_rebalday=Mcap_rebalday.loc[Mcap_rebalday['mcap']>np.percentile(Mcap_rebalday['mcap'],30),:].copy() #If used ThreeFour, then no need to cap 30%mcap
            current_sig=current_sig.loc[current_sig['ticker'].isin(Mcap_rebalday['ticker']),:]
            for sig in selectsigs:
                current_onesigWSMcapDummy,Xset=self.Current_one_signal(sig,current_sig,rebalday,Mcap_rebalday,stock_sector) #Prepare the table with sector dummy and marketcap, to be neutrliazed
                #if sig in ['SectorAlpha','HotSector']:
                #    Xset=['mcap']
                sig_rebalday=DS.Neutralization(current_onesigWSMcapDummy,sig,Xset)                                          #Neutralized sig values
                sig_rebalday=sig_rebalday.rename(columns={'sigvalue':sig})
                sig_rebalday=DS.Winsorize(sig_rebalday,'N_'+sig,0.05) 
                sig_rebalday[sig+'_zscore']=stats.zscore(sig_rebalday['N_'+sig])
                #if sig=='SectorAlpha':
                #    eightypercentile=np.percentile(sig_rebalday[sig+'_zscore'],85) #85 has the best monotonicity so far
                #    sig_rebalday.loc[sig_rebalday[sig+'_zscore']>=eightypercentile,sig+'_zscore']= sig_rebalday.loc[sig_rebalday[sig+'_zscore']>=eightypercentile,sig+'_zscore']-eightypercentile
                nsigdict[sig+'_'+rebalday]=sig_rebalday
        return(nsigdict)
    
    #Factor consists of different signal. given Quality's siginfac=['ROE','ROA'],facname='Quality' 
    #Input: factorname and the signals under the factor. Output the synthesized Zscore of each stock on one Factor
    def Factorscore(self,rebaldaylist,nsigdict,facname,siginfac,factorZ):
        siginfacz=[sig+'_zscore' for sig in siginfac]
        for rebalday in rebaldaylist:
            print(rebalday)
            zscoretab=pd.DataFrame(nsigdict[siginfac[0]+'_'+rebalday]['ticker'],columns=['ticker'])
            for sig in siginfac:
                zscoretab=pd.merge(zscoretab,nsigdict[sig+'_'+rebalday][['ticker',sig,'N_'+sig,sig+'_zscore']],on='ticker',how='outer')
            #zscoretab=zscoretab.dropna()
            #zscoretab=zscoretab.reset_index(drop=True)
            zscoretab[facname+'_zscore']=np.nanmean(zscoretab[siginfacz],axis=1)
            zscoretab=zscoretab.replace([np.inf, -np.inf], np.nan)
            zscoretab=zscoretab.dropna()
            if len(siginfacz)>1:
                zscoretab[facname+'_zscore']=stats.zscore(zscoretab[facname+'_zscore'])
            zscoretab['Q']=pd.qcut(zscoretab[facname+'_zscore'],5,labels=[1,2,3,4,5],duplicates='drop')  #return the grouping of the signame column of a dataframe
            factorZ[facname+'_'+rebalday]=zscoretab
        return(factorZ)
    
    #convert the qdict into portfolio holdings 
    def Portdict(self,olddict,rebaldaylist):
        itemlist=olddict.keys()
        facnamelist=[x.split('_')[0]for x in itemlist]
        facnamelist=list(set(facnamelist))
        portdict={}
        for fac in facnamelist:
            portdict=DS.Facqport(olddict,fac,rebaldaylist,portdict)
        portdict={k:pd.DataFrame(v,columns=['ticker','date','PortNav%'])for k,v in portdict.items()}
        return(portdict)
    
    #Produce the Fzdict (each factor's zscore on every stock on ONE rebalday: 'Quality_2019-05-06')
    def Fzdict(self,dailyreturn,rebaldaylist,facdict):
        selectsigs=[]
        [selectsigs.extend(v) for k, v in facdict.items()]
        siglist=list(set([x.replace('growth','') for x in selectsigs]))
        siglist=list(set([x.replace('vol','') for x in siglist]))     #the original signal before 'growth','vol'
        facnamelist=list(facdict.keys())                              #factors
        #rebaldaylist=DC.Rebaldaylist(startdate,rebal_period)
        sighist=self.P.SigdataPrep(dailyreturn,siglist,rebaldaylist)                                #All fundadata of basic signals
        sighist=DS.GrowVol(sighist,'grow')                                                          #All growthdata of basic signals
        nsigdict=self.NSighist(dailyreturn,rebaldaylist,sighist,selectsigs)                         #Neutralize selected signals over rebaldaylist
        fzdict={}
        for facname in facnamelist:
            siginfac=facdict[facname]
            fzdict=self.Factorscore(rebaldaylist,nsigdict,facname,siginfac,fzdict)                #calculate added zscore of factor and Group it into 5Q
        return(fzdict)
        
    #The TEST module is used to take intersection of ThreeFouR (Analyst rating 3+, generated by TAfour in AnalystStock.py)
    #Produce the Fzdict (each factor's zscore on every stock on ONE rebalday: 'Quality_2019-05-06')
    def FzdictTEST(self,dailyreturn,rebaldaylist,facdict,ThreeFour):
        selectsigs=[]
        [selectsigs.extend(v) for k, v in facdict.items()]
        siglist=list(set([x.replace('growth','') for x in selectsigs]))
        siglist=list(set([x.replace('vol','') for x in siglist]))
        facnamelist=list(facdict.keys())
        sighist=self.P.SigdataPrep(dailyreturn,siglist,rebaldaylist)                                #All fundadata of basic signals
        sighist=DS.GrowVol(sighist,'grow')                                                          #All growthdata of basic signals
        nsigdict=self.NSighistTEST(dailyreturn,rebaldaylist,sighist,selectsigs,ThreeFour)                       #Neutralize selected signals over rebaldaylist
        fzdict={}
        for facname in facnamelist:
            siginfac=facdict[facname]
            fzdict=self.Factorscore(rebaldaylist,nsigdict,facname,siginfac,fzdict)                #calculate added zscore of factor and Group it into 5Q
        return(fzdict)
        
    #Merge each stock's factors' zscore(not signals') together in time series, all in one table 
    def FZtab(self,fzdict):
        itemlist=fzdict.keys()
        facnamelist=list(set([x.split('_')[0]for x in itemlist]))
        rebaldaylist=list(set([x.split('_')[1]for x in itemlist]))
        rebaldaylist.sort()
        colnames=['date','ticker']+[x+'_zscore'for x in facnamelist]
        fztab=pd.DataFrame(columns=colnames)
        for rebalday in rebaldaylist:
            rebalztab=pd.DataFrame()
            for facname in facnamelist:
                ztab=fzdict[facname+'_'+rebalday][['ticker',facname+'_zscore']].copy()
                if rebalztab.shape[0]==0:
                   rebalztab=ztab.copy()
                else:
                   rebalztab=pd.merge(rebalztab,ztab,on='ticker',how='outer')
            rebalztab.insert(0,column='date',value=rebalday)            
            fztab=fztab.append(rebalztab)
        #fztab=fztab.drop('index', 1)
        return(fztab)
            
    #dailyreturn=DC.Dailyreturn_retrieve()
    #startdate='2006-12-28'
    #rebal_period=20
    #facdict={'Quality': ['ROETTM', 'ROATTM'],'Growth': ['QRevenuegrowth', 'QNetprofitgrowth'],'Value': ['PE', 'PB', 'PS']}
    #facdict={'Quality': ['ROETTM'],'Growth': ['QRevenuegrowth'],'Value': ['PE']}
    #facdict={'Quality': ['ROETTM', 'ROATTM'],'Growth': ['QRevenuegrowth', 'QNetprofitgrowth'],'Value': ['PE', 'PB', 'PS'],'Market':['turnoverweek']}
    #facdict={'Sector':['SectorAlpha']}
    #facdict={'Quality': ['ROETTM', 'ROATTM'],'Growth': ['QRevenuegrowth', 'QNetprofitgrowth'],'Value': ['PE', 'PB', 'PS'],'Market':['turnoverweek'],'Sector':['SectorAlpha']}
class Review():
    def __init__(self):
        self.P=Prep()
        self.F=Funda()
    
    #The process of Backtest on Factor level (each factor consists of different signals)
    def FundaBT(self,dailyreturn,startdate,rebal_period,facdict):
        rebaldaylist=DC.Rebaldaylist(startdate,rebal_period)
        fzdict=self.F.Fzdict(dailyreturn,rebaldaylist,facdict)
        itemlist=fzdict.keys()
        rebaldaylist=list(set([x.split('_')[1]for x in itemlist]))
        rebaldaylist.sort()                                                                         
        portdict=self.F.Portdict(fzdict,rebaldaylist)                                               ##calculate added zscore of factor and Group it into 5Q,Generate each Factor's holdings
        PNLcumdict=self.P.PNLC(dailyreturn,portdict)                                                #Calculate each factors' 5 PNL lines
        return(PNLcumdict,portdict)
      
      #The TEST module is used to take intersection of Universe like ThreeFouR (Analyst rating 3+, generated by TAfour in AnalystStock.py)  
      #The process of Backtest on Factor level (each factor consists of different signals)
    def FundaBTTEST(self,dailyreturn,rebaldaylist,facdict):
        facinfacz=[x+'_zscore' for x in facdict.keys()]
        ThreeFour=pd.read_csv("D:/SecR/ThreeFour.csv")
        ThreeFour['ticker']=[str(x).zfill(6)for x in ThreeFour['ticker']]
        ThreeFour=ThreeFour.drop_duplicates()
        rebaldaylist=list(ThreeFour['date'].unique())
        fzdict=self.F.FzdictTEST(dailyreturn,rebaldaylist,facdict,ThreeFour)                                                             
        fztab=self.F.FZtab(fzdict)
        fztab['meanscore']=np.nanmean(fztab[facinfacz],axis=1) #included those dont have score in a factor
        olddict={}
        for rebalday in rebaldaylist:
            rebalz=fztab.loc[fztab['date']==rebalday,:].copy()
            rebalz['rank']=rebalz['meanscore'].rank(method='first')
            rebalz['Q']=pd.qcut(rebalz['rank'].values,5,labels=[1,2,3,4,5])
            olddict['meanscore_'+rebalday]=rebalz
        portdict=self.F.Portdict(olddict,rebaldaylist)                                               ##calculate added zscore of factor and Group it into 5Q,Generate each Factor's holdings
        PNLcumdict=self.P.PNLC(dailyreturn,portdict)                                                #Calculate each factors' 5 PNL lines
        return(PNLcumdict,portdict,fzdict)
    
    #Pairwise tesitng of Sector and Signals
    def SectorSignal(self,dailyreturn):
        startdate='2005-12-28'
        rebal_period=20
        signallist=pd.read_csv("D:/SecR/Signallist.csv")
        sectorlist=DC.Sec_name('CSI')['sector']
        rebaldaylist1=DC.Rebaldaylist(startdate,rebal_period)
        NewSummarytab=pd.DataFrame(columns=['date',1,2,3,4,5,'signal','sector'])
        for sector in sectorlist:
            Summarytab=[]
            print(sector)
            universe=DC.Sector_stock(rebaldaylist1,[sector],'CSI')
            for i in range(0,signallist.shape[0]):
                facdict={}
                facdict[signallist.iloc[i,0]]=[signallist.iloc[i,1]]
                PNLcumdict,portdict=self.FundaBTTEST(dailyreturn,startdate,rebal_period,facdict,universe)
                newtab=list(PNLcumdict[signallist.iloc[i,0]].iloc[-1,:])
                newtab.append(signallist.iloc[i,1])
                newtab.append(sector)
                Summarytab.append(newtab)
            DFSummarytab=pd.DataFrame(Summarytab,columns=['date',1,2,3,4,5,'signal','sector'])
            NewSummarytab=NewSummarytab.append(DFSummarytab)
            NewSummarytab.to_csv("D:/MISC/Summarytab.csv",index=False)
        return(Summarytab) 
    
    #Backtest on integrated level, sum-up zscore of every factor, take Q1
    def IntegratedBT(self,dailyreturn,rebaldaylist,facdict):
        facinfacz=[x+'_zscore' for x in facdict.keys()]
        fzdict=self.F.Fzdict(dailyreturn,rebaldaylist,facdict)
        #ThreeFour=pd.read_csv("D:/SecR/ThreeFour.csv")
        #fzdict=self.F.FzdictTEST(dailyreturn,rebaldaylist,facdict,ThreeFour)
        fztab=self.F.FZtab(fzdict)
        fztab['meanscore']=np.nanmean(fztab[facinfacz],axis=1) #included those dont have score in a factor
        olddict={}
        for rebalday in rebaldaylist:
            rebalz=fztab.loc[fztab['date']==rebalday,:].copy()
            rebalz['rank']=rebalz['meanscore'].rank(method='first')
            rebalz['Q']=pd.qcut(rebalz['rank'].values,5,labels=[1,2,3,4,5])
            olddict['meanscore_'+rebalday]=rebalz
        portdict=self.F.Portdict(olddict,rebaldaylist)
        PNLcumdict=self.P.PNLC(dailyreturn,portdict)             
        return(PNLcumdict)
        
        
    #portdict=self.FundaBT(dailyreturn,startdate,rebal_period,facdict) 
    #The 3-4-5 group of each factor 并集
    def Filter(self,portdict):
        itemlist=portdict.keys()
        facnamelist=list(set([x.split('_')[0]for x in itemlist]))
        facgoodstocks={}
        shortlist=[]
        for fac in facnamelist:
            facgoodstocks[fac]=portdict[fac+'_4'][['ticker','date']].append(portdict[fac+'_5'][['ticker','date']])
            facgoodstocks[fac]=facgoodstocks[fac].append(portdict[fac+'_3'][['ticker','date']])
            facgoodstocks[fac]['index']=facgoodstocks[fac]['ticker']+facgoodstocks[fac]['date']
            if len(shortlist)==0:
                shortlist=facgoodstocks[fac]['index']
            else:
                shortlist=list(set(shortlist)&set(facgoodstocks[fac]['index']))                       #Use the index=[date+ticker] as a filter, take intersection of index
        shortlistdf=pd.DataFrame(shortlist,columns=['index'])
        shortlistdf['date']=shortlistdf['index'].str[6:]
        shortlistdf['ticker']=shortlistdf['index'].str[0:6]
        shortlistdf=shortlistdf.sort_values(by=['date','ticker'],ascending=[True,True])
        shortlistdf = shortlistdf.drop('index', 1)
        return(shortlistdf)
    
    #Generated the intersection of shortlistdf (3+ in multifactors) with CSI300,500,800.    
    #PNLCumdict,portdict=R.FundaBT(dailyreturn,startdate,rebal_period,facdict)
    #BM-intersected Equally weighted model portfolios 
    def BMIntersec(self,dailyreturn,portdict,startdate,benchmark):
        shortlistdf=self.Filter(portdict)
        shortlist_intersec=WS.Benchmark_intersect(shortlistdf,benchmark)
        shortlistpostab=WS.Generate_PortNav(shortlist_intersec)
        SPNL=RC.DailyPNL(dailyreturn,shortlistpostab)
        #PNL['CumReturn']=np.exp(np.log1p(PNL['dailyreturn']).cumsum())
        
        shortlistpostabEq=WS.Generate_PortNavEqual(shortlist_intersec)
        SPNLEq=RC.DailyPNL(dailyreturn,shortlistpostabEq)
        SPNLEq=SPNLEq.rename(columns={'dailyreturn':'EQdailyreturn'})
        
        BM_memb=DC.Benchmark_membs(benchmark,startdate)
        postabBM=WS.Generate_PortNav(BM_memb)
        SPNLBM=RC.DailyPNL(dailyreturn,postabBM)
        SPNLBM=SPNLBM.rename(columns={'dailyreturn':'BMdailyreturn'})
        Comptab=pd.merge(SPNL,SPNLEq,on='date',how='left')
        Comptab=pd.merge(Comptab,SPNLBM,on='date',how='left')
        Comptab['StratCum']=np.exp(np.log1p(Comptab['dailyreturn']).cumsum())
        Comptab['StratEqCum']=np.exp(np.log1p(Comptab['EQdailyreturn']).cumsum())
        Comptab['BenchMarkCum']=np.exp(np.log1p(Comptab['BMdailyreturn']).cumsum())
        return(Comptab)

    #Loop through Fzdict to conduct Nuetralized sector/marketcap pure mimicking portfolio on each rebalday 
    def NeutralFactor(self,dailyreturn,fzdict,benchmark,targetfactor):
        itemlist=fzdict.keys()
        facnamelist=list(set([x.split('_')[0]for x in itemlist]))
        rebaldaylist=list(set([x.split('_')[1]for x in itemlist]))
        rebaldaylist.sort()
        portdict={}
        rdailyreturn=dailyreturn.loc[dailyreturn['date'].isin(rebaldaylist),:].copy()
        rdailyreturn['mcap']=rdailyreturn['mcap'].apply(np.log)
        tickers=[v['ticker']for k,v in fzdict.items()]
        tickerlist=list(set(list(chain(*tickers))))
        stock_sector=DC.Stock_sector(rebaldaylist,tickerlist,'CITIC')
        rdailyreturn,stock_sector=map(DS.Addindex,(rdailyreturn,stock_sector))
        for facname in facnamelist:
            portdict=DS.Facport(fzdict,facname,rebaldaylist,portdict)
            portdict[facname]['index']=portdict[facname]['date']+portdict[facname]['ticker']
            portdict[facname]=pd.merge(portdict[facname],rdailyreturn[['index','mcap']],on='index',how='left')
            portdict[facname]=pd.merge(portdict[facname],stock_sector[['index','primecode']],on='index',how='left') #Add Sector
            indu_dummy=pd.get_dummies(portdict[facname]['primecode'])
            portdict[facname]=pd.concat([portdict[facname],indu_dummy],axis=1)  
            bm=WS.Benchmark_intersect(portdict[facname],benchmark)
            porthist=portdict[facname].loc[portdict[facname]['Q']==5,:].copy()
            for rebalday in rebaldaylist:
                porthist_rebal,bm_rebal=map(lambda df: df.loc[df['date']==rebalday,:].copy(),[porthist,bm])
                porthist_rebal['weight']=0
                colnames=['ticker','weight',targetfactor]
                Xset=['mcap']+list(indu_dummy.columns)
                colnames.extend(Xset)
                porthist_rebal,bm_rebal=map(lambda df: df[colnames],[porthist_rebal,bm_rebal])
        return(portdict)
    
    #Reconstruct the fzdict(Factor RebalDay Zscore), othogonize them on
    def BT_Otho(self,fzdict,dailyreturn):
        itemlist=fzdict.keys()
        facnamelist=list([x.split('_')[0]for x in itemlist])
        rebaldaylist=list([x.split('_')[1]for x in itemlist])
        rebaldaylist.sort()
        newfzdict={}
        for rebalday in rebaldaylist:
            tobeo=pd.DataFrame()
            for facname in facnamelist:
                ztab=fzdict[facname+'_'+rebalday][['ticker',facname+'_zscore']].copy()
                if tobeo.shape[0]==0:
                    tobeo=ztab.copy()
                else:
                    tobeo=pd.merge(tobeo,ztab,on='ticker',how='outer')
            othoq=DS.Othogonize(tobeo)
            for facname in facnamelist:
                othoq['Q']=pd.qcut(othoq[facname+'_zscore'],5,labels=[1,2,3,4,5])
                newfzdict[facname+'_'+rebalday]=othoq[['ticker','Q']]
        portdict=self.F.Portdict(newfzdict,rebaldaylist)
        PNLcumdictNew=self.P.PNLC(dailyreturn,portdict)
        return(PNLcumdictNew,portdict,newfzdict)
    


#Use WLS constrianted to get pure factor return of each sector/style and market following BARRA CNE5 model              
class FactorReturn():
    def __init__(self):
        self.P=Prep()
        self.F=Funda()
    
    #Produce the Fzdict (each factor's zscore on every stock on ONE rebalday: 'Quality_2019-05-06')
    def Period_Fzdict(self,dailyreturn,rebaldaylist,facdict):
        selectsigs=[]
        [selectsigs.extend(v) for k, v in facdict.items()]
        siglist=list(set([x.replace('growth','') for x in selectsigs]))
        siglist=list(set([x.replace('vol','') for x in siglist]))
        facnamelist=list(facdict.keys())
        sighist=self.P.SigdataPrep(dailyreturn,siglist,rebaldaylist)                                #All fundadata of basic signals
        sighist=DS.GrowVol(sighist,'grow')                                                          #All growthdata of basic signals
        nsigdict=self.F.NSighist(dailyreturn,rebaldaylist,sighist,selectsigs)                       #Neutralize selected signals over rebaldaylist
        fzdict={}
        for facname in facnamelist:
            siginfac=facdict[facname]
            fzdict=self.F.Factorscore(rebaldaylist,nsigdict,facname,siginfac,fzdict)                #calculate added zscore of factor and Group it into 5Q
        return(fzdict)
    
    #Factor return of each day. Run Cross-sectional regression on daily basis 
    def Period_facreturn(self,fztab,rebalday,returnday,dailyreturn,stock_sector):
        fztabrebal=fztab.loc[fztab['date']==rebalday,:]
        fztabrebal=fztabrebal.dropna()
        fztabrebal=fztabrebal.reset_index(drop=True)
        othorebal=DS.Othogonize(fztabrebal.drop('date',1))    
        othorebal['date']=rebalday                                                #先正交化Factor exposure
        othorebal['country']=1
        othorebal=DS.Mcap_sector(stock_sector,dailyreturn,othorebal)
        pnlrebal=DC.Period_PNL(dailyreturn,othorebal,returnday,returnday)
        othorebal=pd.merge(othorebal,pnlrebal[['ticker','dailyreturn']],on=['ticker'],how='left')
        othorebal=othorebal.dropna()
        industry_weight=pd.DataFrame(othorebal.groupby(['primecode'])['mcap'].sum())          #industry_weight: the every sector's mcap as ratio vs the last industry
        industry_weight.reset_index(inplace=True)
        industry_weight['w']=-industry_weight['mcap']/industry_weight.iloc[industry_weight.shape[0]-1,industry_weight.shape[1]-1]
        #othorebal['Size_zscore']=stats.zscore(othorebal['mcap'])
        othorebal=othorebal.dropna()
        facs=list(fztab.columns)
        facs.remove('date')
        facs.remove('ticker')
        Xset=facs+['country']+sorted(set(othorebal['primecode'])) #Xset: all columns used to do the matrix operation for 因子收益calculation
        X=othorebal[Xset].copy()                                                                   #Othorebal: has everything including ticker and date, mcap....
        f=Opt.WLS_adjusted(othorebal,industry_weight,X)                    #W is a matrix of 15x2577                                                            
        return(f,Xset)                                                       #W的定义：对 CNE5 模型求解的对象是每个因子的投资组合中所有股票的配比权重
                                                                             #对于每一个因子，该因子上所有W之和为0
    #loop through it EVERYDAY over the historical period 
    def Facreturn(self,startdate,dailyreturn):
        totalrebaldaylist=DC.Rebaldaylist(startdate,1)
        rebalperiodlist = [totalrebaldaylist[x:x+60] for x in range(0, len(totalrebaldaylist),60)]
        returnperiodlist= [totalrebaldaylist[x:x+60] for x in range(1, len(totalrebaldaylist),60)]
        facdict={'Quality': ['ROETTM', 'ROATTM'],'Growth': ['QRevenuegrowth', 'QNetprofitgrowth'],'Value': ['PE', 'PB', 'PS'],'Market':['turnoverweek']}
        facreturn=pd.DataFrame()
        for i in range(0,(len(rebalperiodlist)-1)):
            rebaldaylist=rebalperiodlist[i]
            returndaylist=returnperiodlist[i]
            subdict=dict(zip(rebaldaylist,returndaylist))
            fzdict=self.Period_Fzdict(dailyreturn,rebaldaylist,facdict)
            fztab=self.F.FZtab(fzdict)
            tickerlist=fztab['ticker'].unique()
            stock_sector=DC.Stock_sector(rebaldaylist,tickerlist,'CSI')
            periodfacreturn=[]
            for rebalday in rebaldaylist:
                returnday=subdict[rebalday]
                f,Xset=self.Period_facreturn(fztab,rebalday,returnday,dailyreturn,stock_sector)
                periodfacreturn.append(f)
            periodfacreturndf=pd.DataFrame(periodfacreturn,columns=Xset)
            periodfacreturndf['date']=rebaldaylist
            facreturn=facreturn.append(periodfacreturndf)
            facreturn.to_csv("D:/MISC/FactorReturn/facreturn_"+rebalday+".csv",index=False)
        return(facreturn)
    
    def Rtest(self,startdate,dailyreturn):
        rebaldaylist=DC.Rebaldaylist(startdate,20)
        activestock=dailyreturn.loc[(dailyreturn['date'].isin(rebaldaylist))&(dailyreturn['dailyreturn']!=0),:].copy()
        mcaprebal=pd.DataFrame()
        for rebalday in rebaldaylist:
            rebaldayactivestock=activestock.loc[activestock['date']==rebalday,:].copy()
            Mcap_rebalday=rebaldayactivestock.loc[rebaldayactivestock['mcap']>np.percentile(rebaldayactivestock['mcap'],30),:].copy()
            Mcap_rebalday['PortNav%']=1/Mcap_rebalday.shape[0]
            mcaprebal=mcaprebal.append(Mcap_rebalday)
        portPNL=RC.DailyPNL(dailyreturn,mcaprebal)
        allshsreturn=np.exp(np.log1p(portPNL['dailyreturn']).cumsum())
        return(allshsreturn)
        
    
    
 