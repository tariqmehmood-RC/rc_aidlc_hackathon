import * as fs from 'fs';
import * as path from 'path';
import * as cdk from 'aws-cdk-lib';
import { REGION, createApp } from '../lib/app';
import { placeholderBundle } from './helpers';

const STACK_NAMES = ['AuthStack', 'DataStack', 'ApiStack', 'WebStack'];

function stacksOf(app: cdk.App): cdk.Stack[] {
  return app.node.children.filter((c): c is cdk.Stack => c instanceof cdk.Stack);
}

describe('app', () => {
  const bundle = placeholderBundle();

  test('has exactly the four stacks, with project-prefixed stack names', () => {
    const stacks = stacksOf(createApp({ backendCodePath: bundle }));
    expect(stacks.map((s) => s.node.id).sort()).toEqual([...STACK_NAMES].sort());
    expect(stacks.map((s) => s.stackName).sort()).toEqual(
      ['InsideSalesCopilot-Api', 'InsideSalesCopilot-Auth', 'InsideSalesCopilot-Data', 'InsideSalesCopilot-Web'],
    );
  });

  test('every stack is pinned to us-east-1', () => {
    for (const stack of stacksOf(createApp({ backendCodePath: bundle }))) expect(stack.region).toBe('us-east-1');
    expect(REGION).toBe('us-east-1');
  });

  test('region is not taken from the shell', () => {
    const saved = { r: process.env.AWS_REGION, d: process.env.AWS_DEFAULT_REGION, c: process.env.CDK_DEFAULT_REGION };
    process.env.AWS_REGION = process.env.AWS_DEFAULT_REGION = process.env.CDK_DEFAULT_REGION = 'eu-west-1';
    try {
      for (const stack of stacksOf(createApp({ backendCodePath: bundle }))) expect(stack.region).toBe('us-east-1');
    } finally {
      for (const [k, v] of [['AWS_REGION', saved.r], ['AWS_DEFAULT_REGION', saved.d], ['CDK_DEFAULT_REGION', saved.c]] as const) {
        if (v === undefined) delete process.env[k]; else process.env[k] = v;
      }
    }
  });

  test('a missing Lambda bundle gives a clear error', () => {
    expect(() => createApp({ backendCodePath: '/nonexistent' })).toThrow(/Run scripts\/build_backend.sh first/);
  });
});

describe('cdk.json context', () => {
  const cdkJson = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'cdk.json'), 'utf-8'));

  test('research user agent names the project and the team repo, not a person', () => {
    expect(cdkJson.context.researchUserAgent).toBe(
      'InsideSalesCopilot/0.1 (Royal Cyber AWS AI-DLC hackathon; +https://github.com/tariqmehmood-RC/rc_aidlc_hackathon)',
    );
  });

  test('brief model is haiku or sonnet', () => {
    expect(['haiku', 'sonnet']).toContain(cdkJson.context.briefModel);
  });

  test('model IDs are the tested defaults', () => {
    expect(cdkJson.context.haikuModelId).toBe('us.anthropic.claude-haiku-4-5-20251001-v1:0');
    expect(cdkJson.context.sonnetModelId).toBe('us.anthropic.claude-sonnet-5');
  });

  test('Bedrock regions are exactly where the us. profiles route', () => {
    expect(cdkJson.context.bedrockRegions).toEqual(['us-east-1', 'us-east-2', 'us-west-2']);
  });
});
