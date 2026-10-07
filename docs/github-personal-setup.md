# 개인 GitHub 계정 분리

커밋 작성자(`user.name`, `user.email`)와 GitHub에 접속하는 인증 계정은 별개다. 둘 모두 개인 계정에 맞춰 설정한다. 회사 전역 설정을 바꾸지 않고 이 저장소에만 설정하는 방식을 사용한다.

아래 명령은 절차 예시이며 아직 실행하지 않았다. 대문자 자리표시자를 실제 값으로 교체한다.

## 1. 개인 전용 SSH 키

```sh
mkdir -p ~/.ssh
chmod 700 ~/.ssh
ssh-keygen -t ed25519 -C "PERSONAL_EMAIL" -f ~/.ssh/id_ed25519_github_personal
```

기존 파일이 있으면 덮어쓰지 않는다. 생성한 `.pub` 공개키를 개인 GitHub 계정의 Settings → SSH and GPG keys에 등록한다. 비밀키는 업로드하거나 저장소에 넣지 않는다.

## 2. 저장소 전용 설정

이 저장소 루트에서 실행한다.

```sh
git config --local user.name "PERSONAL_NAME"
git config --local user.email "PERSONAL_EMAIL"
git config --local core.sshCommand 'ssh -i ~/.ssh/id_ed25519_github_personal -o IdentitiesOnly=yes -F /dev/null'
```

이 명령은 이 저장소의 `.git/config`에만 기록한다. 이메일은 개인 GitHub 계정에 등록한 이메일이나 해당 계정의 noreply 이메일을 사용한다. 전용 키만 사용하도록 지정하여 다른 계정의 키 선택을 피한다. 회사 네트워크에서 프록시 등 별도 SSH 설정이 필요하면 접속 조건에 맞게 조정한다.

## 3. 인증 확인과 원격 연결

```sh
ssh -i ~/.ssh/id_ed25519_github_personal -o IdentitiesOnly=yes -F /dev/null -T git@github.com
```

최초 접속 시 호스트 지문을 GitHub 공식 문서와 확인한다. 응답의 사용자명이 개인 계정인지 확인한다. GitHub는 셸 접속을 제공하지 않아 인증 성공 시에도 종료 코드가 1일 수 있다.

개인 계정으로 GitHub 웹에 로그인하고 빈 저장소를 만든 뒤 연결한다. 공개 여부는 생성 전에 결정한다.

```sh
git remote add origin git@github.com:PERSONAL_USERNAME/REPOSITORY.git
git remote -v
git config --local --get user.name
git config --local --get user.email
git config --local --get core.sshCommand
git add README.md AGENTS.md rules docs .gitignore
git commit -m "Initialize personal agent rules repository"
git push -u origin main
```

이미 origin이 있으면 먼저 값을 확인한다. 저장소 설정과 SSH 키 지정은 clone 시 자동으로 전달되지 않으므로 새 환경에서도 별도로 설정해야 한다.

`gh`의 로그인 상태는 별도다. Git SSH 접속만으로 개인 저장소를 사용할 수 있으므로 회사 `gh` 계정을 전환할 필요는 없다.

## 공식 참고 자료

- [GitHub: 여러 계정 관리](https://docs.github.com/en/account-and-profile/how-tos/account-management/managing-multiple-accounts)
- [GitHub: SSH 연결 테스트](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/testing-your-ssh-connection)
- [GitHub: SSH 키 지문](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints)
