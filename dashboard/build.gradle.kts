val globalArtifactsBuildDir: File by rootProject.extra

tasks {
    val npmBuild by registering(ExecCommandTask::class) {
        command = "npm run-script build"
    }

    register("awsSync", AwsTask::class) {
        dependsOn(npmBuild)
        stage = "stgn"
        profile = if (project.hasProperty("aws.profile")) project.property("aws.profile").toString() else null
    }
}