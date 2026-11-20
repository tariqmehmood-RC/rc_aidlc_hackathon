import * as cdk from 'aws-cdk-lib';
import * as apigw from 'aws-cdk-lib/aws-apigatewayv2';
import { HttpUserPoolAuthorizer } from 'aws-cdk-lib/aws-apigatewayv2-authorizers';
import { HttpLambdaIntegration } from 'aws-cdk-lib/aws-apigatewayv2-integrations';
import * as cloudwatch from 'aws-cdk-lib/aws-cloudwatch';
import * as cognito from 'aws-cdk-lib/aws-cognito';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import { SqsEventSource } from 'aws-cdk-lib/aws-lambda-event-sources';
import * as logs from 'aws-cdk-lib/aws-logs';
import { Construct } from 'constructs';
import { DataStack } from './data-stack';

export interface ApiStackProps extends cdk.StackProps {
  data: DataStack;
  userPool: cognito.IUserPool;
  webClient: cognito.IUserPoolClient;
  /** Folder built by scripts/build_backend.sh. */
  backendCodePath: string;
  haikuModelId: string;
  sonnetModelId: string;
  briefModel: string;
  researchUserAgent: string;
  /** Regions the us. inference profiles may route to. */
  bedrockRegions: string[];
}

type TableName = 'briefs' | 'rules' | 'researchCache';
interface FnSpec {
  id: string;
  handler: string;
  routes: Array<[apigw.HttpMethod, string]>;
  /** Exact DynamoDB actions per table. Index names add access to those indexes only. */
  tables?: Partial<Record<TableName, { actions: string[]; indexes?: string[] }>>;
  sendsJobs?: boolean;
}

/** HTTP API, API Lambdas, the single worker, alarms, and a dashboard (task 5.4). */
export class ApiStack extends cdk.Stack {
  readonly api: apigw.HttpApi;
  readonly worker: lambda.Function;
  readonly functions: Record<string, lambda.Function> = {};

  constructor(scope: Construct, id: string, props: ApiStackProps) {
    super(scope, id, props);
    const { data } = props;
    const code = lambda.Code.fromAsset(props.backendCodePath);
    const tables = { briefs: data.briefs, rules: data.rules, researchCache: data.researchCache };
    const baseEnv = {
      BRIEFS_TABLE: data.briefs.tableName,
      RULES_TABLE: data.rules.tableName,
      RESEARCH_CACHE_TABLE: data.researchCache.tableName,
      JOBS_QUEUE_URL: data.jobs.queueUrl,
      POWERTOOLS_LOG_LEVEL: 'INFO',
    };

    const newFunction = (fnId: string, handler: string, extra: Partial<lambda.FunctionProps> = {}) =>
      new lambda.Function(this, fnId, {
        runtime: lambda.Runtime.PYTHON_3_12,
        architecture: lambda.Architecture.ARM_64,
        code,
        handler,
        memorySize: 256,
        timeout: cdk.Duration.seconds(10),
        environment: baseEnv,
        tracing: lambda.Tracing.ACTIVE,
        logGroup: new logs.LogGroup(this, `${fnId}Logs`, {
          retention: logs.RetentionDays.TWO_WEEKS, // R10.15
          removalPolicy: cdk.RemovalPolicy.DESTROY,
        }),
        ...extra,
      });

    const allowTables = (fn: lambda.Function, spec: FnSpec['tables']) => {
      for (const [name, access] of Object.entries(spec ?? {}) as Array<[TableName, { actions: string[]; indexes?: string[] }]>) {
        const table = tables[name];
        const resources = [table.tableArn, ...(access.indexes ?? []).map((i) => `${table.tableArn}/index/${i}`)];
        fn.addToRolePolicy(new iam.PolicyStatement({ actions: access.actions.map((a) => `dynamodb:${a}`), resources }));
      }
    };

    // --- API functions: they read and write DynamoDB and send jobs. None may call Bedrock (R10.4).
    const specs: FnSpec[] = [
      { id: 'CreateBrief', handler: 'backend.src.handlers.briefs_read.create_brief_handler', routes: [[apigw.HttpMethod.POST, '/api/briefs']],
        tables: { briefs: { actions: ['PutItem', 'UpdateItem'] } }, sendsJobs: true },
      { id: 'ListBriefs', handler: 'backend.src.handlers.briefs_read.list_briefs_handler', routes: [[apigw.HttpMethod.GET, '/api/briefs']],
        tables: { briefs: { actions: ['Query'], indexes: ['byUser'] } } },
      { id: 'GetBrief', handler: 'backend.src.handlers.briefs_read.get_brief_handler', routes: [[apigw.HttpMethod.GET, '/api/briefs/{id}']],
        tables: { briefs: { actions: ['GetItem', 'UpdateItem', 'Query'], indexes: ['byQueue'] } } },
      { id: 'UpdateBrief', handler: 'backend.src.handlers.briefs_write.update_brief_handler', routes: [[apigw.HttpMethod.PUT, '/api/briefs/{id}']],
        tables: { briefs: { actions: ['GetItem', 'UpdateItem'] } } },
      { id: 'ConfirmBrief', handler: 'backend.src.handlers.briefs_write.confirm_brief_handler', routes: [[apigw.HttpMethod.POST, '/api/briefs/{id}/confirm']],
        tables: { briefs: { actions: ['GetItem', 'UpdateItem'] } }, sendsJobs: true },
      { id: 'ApproveBrief', handler: 'backend.src.handlers.briefs_write.approve_brief_handler', routes: [[apigw.HttpMethod.POST, '/api/briefs/{id}/approve']],
        tables: { briefs: { actions: ['GetItem', 'UpdateItem'] } }, sendsJobs: true },
      { id: 'RetryBrief', handler: 'backend.src.handlers.briefs_write.retry_brief_handler', routes: [[apigw.HttpMethod.POST, '/api/briefs/{id}/retry']],
        tables: { briefs: { actions: ['GetItem', 'UpdateItem'] } }, sendsJobs: true },
      { id: 'Rules', handler: 'backend.src.handlers.rules_cases.rules_handler',
        routes: [[apigw.HttpMethod.POST, '/api/briefs/{id}/rules'], [apigw.HttpMethod.GET, '/api/rules'], [apigw.HttpMethod.DELETE, '/api/rules/{ruleId}']],
        tables: { briefs: { actions: ['GetItem', 'UpdateItem'] }, rules: { actions: ['Query', 'PutItem', 'DeleteItem'] } } },
      { id: 'CaseStudies', handler: 'backend.src.handlers.rules_cases.case_studies_handler', routes: [[apigw.HttpMethod.GET, '/api/case-studies']] },
    ];

    // Same-origin through CloudFront, so no CORS. Throttling protects Lambda and DynamoDB.
    this.api = new apigw.HttpApi(this, 'HttpApi', { apiName: 'inside-sales-copilot', createDefaultStage: false });
    this.api.addStage('PublicStage', { stageName: '$default', autoDeploy: true, throttle: { rateLimit: 20, burstLimit: 40 } });
    const authorizer = new HttpUserPoolAuthorizer('Cognito', props.userPool, {
      userPoolClients: [props.webClient],
      identitySource: ['$request.header.Authorization'],
    });

    for (const spec of specs) {
      const fn = newFunction(spec.id, spec.handler);
      allowTables(fn, spec.tables);
      if (spec.sendsJobs) {
        fn.addToRolePolicy(new iam.PolicyStatement({ actions: ['sqs:SendMessage'], resources: [data.jobs.queueArn] }));
      }
      const integration = new HttpLambdaIntegration(`${spec.id}Integration`, fn);
      for (const [method, path] of spec.routes) {
        this.api.addRoutes({ path, methods: [method], integration, authorizer });
      }
      this.functions[spec.id] = fn;
    }

    // --- The worker: the only function that calls Bedrock. One at a time (design 7.3).
    this.worker = newFunction('Worker', 'backend.src.handlers.worker.handler', {
      memorySize: 512,
      timeout: cdk.Duration.seconds(180),
      reservedConcurrentExecutions: 1,
      environment: {
        ...baseEnv,
        BEDROCK_MODEL_HAIKU: props.haikuModelId,
        BEDROCK_MODEL_SONNET: props.sonnetModelId,
        BRIEF_MODEL: props.briefModel,
        RESEARCH_USER_AGENT: props.researchUserAgent,
      },
    });
    allowTables(this.worker, {
      briefs: { actions: ['GetItem', 'UpdateItem'] },
      rules: { actions: ['Query'] },
      researchCache: { actions: ['GetItem', 'PutItem'] },
    });
    this.worker.addEventSource(new SqsEventSource(data.jobs, { batchSize: 1 }));
    const profileArns = [props.haikuModelId, props.sonnetModelId].map(
      (m) => `arn:aws:bedrock:us-east-1:${this.account}:inference-profile/${m}`,
    );
    const modelArns = [props.haikuModelId, props.sonnetModelId].flatMap((m) =>
      props.bedrockRegions.map((r) => `arn:aws:bedrock:${r}::foundation-model/${m.replace(/^us\./, '')}`),
    );
    this.worker.addToRolePolicy(new iam.PolicyStatement({ actions: ['bedrock:InvokeModel'], resources: [...profileArns, ...modelArns] }));
    this.functions.Worker = this.worker;

    // --- Alarms and dashboard (R10.12, D13.2). No notification target yet: alarms show in the console.
    const ns = 'InsideSalesCopilot';
    const dims = { service: 'inside-sales-copilot' };
    const bedrockThrottled = new cloudwatch.Metric({ namespace: ns, metricName: 'BedrockThrottled', dimensionsMap: dims, statistic: 'Sum', period: cdk.Duration.minutes(5) });
    const bedrockCalls = new cloudwatch.Metric({ namespace: ns, metricName: 'BedrockCalls', dimensionsMap: dims, statistic: 'Sum', period: cdk.Duration.minutes(5) });
    const briefs = new cloudwatch.Metric({ namespace: ns, metricName: 'BriefGenerated', dimensionsMap: dims, statistic: 'Sum', period: cdk.Duration.minutes(5) });
    const dlqDepth = data.deadLetters.metricApproximateNumberOfMessagesVisible({ period: cdk.Duration.minutes(1), statistic: 'Maximum' });

    new cloudwatch.Alarm(this, 'DeadLetterQueueNotEmpty', {
      alarmDescription: 'A job failed 3 times and went to the dead-letter queue.',
      metric: dlqDepth, threshold: 0, comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
      evaluationPeriods: 1, treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
    });
    new cloudwatch.Alarm(this, 'WorkerErrors', {
      alarmDescription: 'The worker Lambda raised errors (unexpected crashes).',
      metric: this.worker.metricErrors({ period: cdk.Duration.minutes(5) }), threshold: 0,
      comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD, evaluationPeriods: 1,
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
    });
    new cloudwatch.Alarm(this, 'BedrockThrottling', {
      alarmDescription: 'Bedrock throttled more than 5 calls in 5 minutes.',
      metric: bedrockThrottled, threshold: 5, comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
      evaluationPeriods: 1, treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
    });
    new cloudwatch.Alarm(this, 'ApiServerErrors', {
      alarmDescription: 'The HTTP API returned 5xx responses.',
      metric: this.api.metricServerError({ period: cdk.Duration.minutes(5), statistic: 'Sum' }), threshold: 0,
      comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD, evaluationPeriods: 1,
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
    });

    new cloudwatch.Dashboard(this, 'Dashboard', {
      dashboardName: 'inside-sales-copilot',
      widgets: [
        [
          new cloudwatch.GraphWidget({ title: 'Briefs generated', left: [briefs], width: 8 }),
          new cloudwatch.GraphWidget({ title: 'Bedrock calls and throttles', left: [bedrockCalls, bedrockThrottled], width: 8 }),
          new cloudwatch.GraphWidget({ title: 'Job queue and dead letters', left: [data.jobs.metricApproximateNumberOfMessagesVisible(), dlqDepth], width: 8 }),
        ],
        [
          new cloudwatch.GraphWidget({ title: 'Worker duration (ms)', left: [this.worker.metricDuration({ statistic: 'Maximum' })], width: 8 }),
          new cloudwatch.GraphWidget({ title: 'Worker errors', left: [this.worker.metricErrors()], width: 8 }),
          new cloudwatch.GraphWidget({ title: 'API 4xx / 5xx', left: [this.api.metricClientError(), this.api.metricServerError()], width: 8 }),
        ],
      ],
    });

    new cdk.CfnOutput(this, 'ApiEndpoint', { value: this.api.apiEndpoint });
  }
}
