from django.db import models


class ComplaintList(models.Model):
	no = models.BigAutoField('编号', db_column='No', primary_key=True)
	area = models.CharField('区域', db_column='Area', max_length=100, blank=True)
	date = models.DateTimeField('时间', db_column='Date', null=True, blank=True)
	customer = models.CharField('客户', db_column='Customer', max_length=200, blank=True)
	complaint_type = models.CharField('投诉等级', db_column='ComplaintType', max_length=50, blank=True)
	webbing_type = models.CharField('带型', db_column='WebbingType', max_length=100, blank=True)
	complaint = models.TextField('投诉点', db_column='Complaint', blank=True)
	classification = models.CharField('分类', db_column='Classification', max_length=100, blank=True)
	defect_pictures = models.TextField('投诉图片', db_column='DefectPictures', blank=True)
	root_cause = models.TextField('根本原因', db_column='RootCause', blank=True)
	corrective_action = models.TextField('纠正措施', db_column='CorrectiveAction', blank=True)
	res = models.CharField('责任人', db_column='Res', max_length=100, blank=True)
	completion_time = models.DateTimeField('完成时间', db_column='CompletionTime', null=True, blank=True)
	state = models.CharField('状态', db_column='State', max_length=50, blank=True)
	remark = models.TextField('备注', db_column='Remark', blank=True)

	def __str__(self):
		return str(self.no)

	class Meta:
		db_table = 'complaintlist'
		verbose_name = '客户投诉'
		verbose_name_plural = '客户投诉'
